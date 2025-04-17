import google.generativeai as genai
import json
import yaml
import requests
import logging
import time
import os
import ansible_runner
from datetime import datetime

# Setup logging
logging.basicConfig(
    filename='server_automation.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Konfigurasi API
GEMINI_API_KEY = "<APIKEY-GEMINI>"  # Ganti dengan API key Anda
PROMETHEUS_URL = "http://localhost:9090"  # Sesuaikan dengan alamat Prometheus Anda

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

def get_prometheus_metrics():
    """Mengambil berbagai metrik server dari Prometheus"""
    metrics = {}
    
    # Daftar query untuk mengambil metrik berbeda
    queries = {
        "cpu_usage": "100 - (avg by(instance) (irate(node_cpu_seconds_total{mode='idle'}[5m])) * 100)",
        "memory_usage": "100 * (1 - ((node_memory_MemFree_bytes + node_memory_Cached_bytes + node_memory_Buffers_bytes) / node_memory_MemTotal_bytes))",
        "disk_usage": "100 - ((node_filesystem_avail_bytes{mountpoint='/'} * 100) / node_filesystem_size_bytes{mountpoint='/'})",
        "load_avg": "node_load1",
        "network_receive": "irate(node_network_receive_bytes_total{device!='lo'}[5m])",
        "network_transmit": "irate(node_network_transmit_bytes_total{device!='lo'}[5m])"
    }
    
    try:
        for metric_name, query in queries.items():
            response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})
            response.raise_for_status()
            data = response.json()
            
            if data["status"] == "success" and data["data"]["result"]:
                # Ambil nilai metrik dari hasil query
                metric_value = float(data["data"]["result"][0]["value"][1])
                metrics[metric_name] = metric_value
            else:
                logging.warning(f"Tidak ada data untuk metrik {metric_name}")
                metrics[metric_name] = None
                
        # Tambahkan timestamp
        metrics["timestamp"] = datetime.now().isoformat()
        return metrics
        
    except Exception as e:
        logging.error(f"Error saat mengambil metrik: {str(e)}")
        return {}

def analyze_with_gemini(metrics):
    """Menganalisis metrik server menggunakan Gemini AI"""
    try:
        prompt = f"""
        Sebagai AI untuk otomatisasi server, analisis metrik berikut dan berikan rekomendasi:
        
        {json.dumps(metrics, indent=2)}
        
        Berikan output dalam format JSON dengan struktur berikut:
        {{
            "status": "healthy|warning|critical",
            "analysis": "Ringkasan kondisi server",
            "issues": [
                {{
                    "component": "cpu|memory|disk|network",
                    "severity": "low|medium|high",
                    "description": "Deskripsi masalah"
                }}
            ],
            "recommendations": [
                {{
                    "action": "restart_service|optimize_config|scale_resources|alert_admin",
                    "description": "Langkah yang perlu diambil",
                    "ansible_task": "Task Ansible dalam format YAML jika diperlukan"
                }}
            ]
        }}
        
        Fokus pada masalah yang memerlukan perhatian segera. Jika server dalam kondisi normal,
        kembalikan status "healthy" dengan analysis yang sesuai.
        """
        
        response = model.generate_content(prompt)
        
        # Dapatkan text dari respons
        response_text = response.text
        
        # Debug: Log respons mentah
        logging.info(f"Raw response from Gemini: {response_text[:100]}...")
        
        # Coba ekstraksi JSON dari respons
        # Kadang Gemini menambahkan teks di luar JSON, jadi kita coba ekstrak
        try:
            # Cari tanda kurung kurawal pertama dan terakhir untuk ekstrak JSON
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                result = json.loads(json_str)
            else:
                # Jika tidak menemukan format JSON, buat struktur manual
                logging.warning("Tidak menemukan format JSON dalam respons Gemini, membuat struktur manual")
                result = {
                    "status": "unknown",
                    "analysis": "Tidak dapat menganalisis respons Gemini",
                    "issues": [],
                    "recommendations": []
                }
        except json.JSONDecodeError as je:
            logging.error(f"Error parsing JSON from response: {je}")
            result = {
                "status": "error",
                "analysis": f"Error parsing JSON: {je}",
                "issues": [],
                "recommendations": []
            }
            
        logging.info(f"Analisis selesai. Status: {result.get('status', 'unknown')}")
        return result
        
    except Exception as e:
        logging.error(f"Error saat menganalisis dengan Gemini: {str(e)}")
        return {
            "status": "error",
            "analysis": f"Terjadi kesalahan saat analisis: {str(e)}",
            "issues": [],
            "recommendations": []
        }

def execute_ansible_task(task_yaml):
    """Menjalankan task Ansible dari rekomendasi"""
    try:
        # Buat direktori untuk data Ansible
        ansible_dir = './ansible'
        os.makedirs(ansible_dir, exist_ok=True)
        
        # Tulis task ke file playbook temporary
        playbook_content = {
            "name": "Auto-remediation",
            "hosts": "localhost",
            "tasks": [yaml.safe_load(task_yaml)]
        }
        
        # Simpan playbook ke file
        playbook_file = "auto_remediation.yml"
        with open(playbook_file, "w") as f:
            yaml.dump(playbook_content, f)
        
        # Jalankan playbook
        result = ansible_runner.run(
            playbook=playbook_file,
            private_data_dir=ansible_dir,
            verbosity=1
        )
        
        return {
            "status": result.status,
            "rc": result.rc,
            "stats": result.stats
        }
        
    except Exception as e:
        logging.error(f"Error saat menjalankan Ansible task: {str(e)}")
        return {"status": "failed", "error": str(e)}

def identify_high_resource_service():
    """Mengidentifikasi layanan dengan penggunaan CPU tertinggi yang aman untuk di-restart"""
    try:
        # Dapatkan beberapa proses dengan CPU tertinggi (tidak hanya 1)
        cmd = "ps -eo pid,ppid,cmd,%cpu,%mem --sort=-%cpu | head -10"
        process_info = os.popen(cmd).read().strip().split('\n')
        
        # Skip header
        process_info = process_info[1:]
        
        # Daftar string yang menandakan proses sistem kritis
        critical_processes = ['init', 'systemd', 'kernel', 'kthreadd', 'kworker', 
                             'sshd', 'bash', 'python3 server_automation.py', 'prometheus']
        
        # Periksa setiap proses dari yang CPU tertinggi
        for process in process_info:
            parts = process.split()
            if len(parts) >= 5:
                pid = parts[0]
                cmd_str = ' '.join(parts[2:])
                cpu_pct = float(parts[-2])
                
                # Skip proses dengan CPU rendah
                if cpu_pct < 5.0:
                    continue
                    
                # Skip proses kritis
                is_critical = False
                for critical in critical_processes:
                    if critical in cmd_str:
                        is_critical = True
                        break
                
                if is_critical:
                    logging.info(f"Melewati proses kritis: {cmd_str}")
                    continue
                
                # Coba identifikasi service
                if '/' in cmd_str:
                    cmd_name = cmd_str.split('/')[-1].split()[0]
                else:
                    cmd_name = cmd_str.split()[0]
                
                # Cek apakah ini adalah service yang bisa di-restart
                find_service_cmd = f"systemctl list-units --type=service | grep -i {cmd_name} | head -1 | awk '{{print $1}}'"
                potential_service = os.popen(find_service_cmd).read().strip()
                
                if potential_service and potential_service.endswith('.service'):
                    service_name = potential_service[:-8]  # Hapus .service
                    logging.info(f"Menemukan layanan untuk di-restart: {service_name} (CPU: {cpu_pct}%)")
                    return service_name
                    
                # Jika bukan service, coba lihat apakah ini proses aplikasi yang aman di-kill
                logging.info(f"Proses non-service dengan CPU tinggi: {cmd_str} (PID: {pid}, CPU: {cpu_pct}%)")
                
                # Cek apakah bukan proses root
                user_cmd = f"ps -o user= -p {pid}"
                user = os.popen(user_cmd).read().strip()
                
                if user != "root" and cpu_pct > 30.0:
                    logging.info(f"Menemukan proses non-kritiss dengan CPU tinggi: PID {pid}, User {user}, CMD {cmd_str}")
                    return f"process:{pid}"  # Tanda khusus untuk menunjukkan ini proses bukan service
        
        # Cek common services jika tidak menemukan proses dengan CPU tinggi
        common_services = ["apache2", "nginx", "mysql", "postgresql", "php-fpm", "memcached"]
        for service in common_services:
            check_cmd = f"systemctl is-active {service} 2>/dev/null"
            is_active = os.popen(check_cmd).read().strip()
            if is_active == "active":
                logging.info(f"Menemukan layanan umum aktif: {service}")
                return service
                
        logging.warning("Tidak dapat mengidentifikasi proses atau layanan yang aman untuk di-restart")
        return None
                
    except Exception as e:
        logging.error(f"Error saat mengidentifikasi layanan: {str(e)}")
        return None
        
        
def send_telegram_notification(message, token="<ID-TOKEN>", chat_id="<ID-CHAT>"):
    """Mengirim notifikasi ke Telegram"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, data=payload)
        response.raise_for_status()
        
        logging.info(f"Notifikasi Telegram berhasil dikirim: {response.status_code}")
        return {"status": "success", "response": response.json()}
    except Exception as e:
        logging.error(f"Gagal mengirim notifikasi Telegram: {str(e)}")
        return {"status": "failed", "error": str(e)}


def format_notification_message(analysis, execution_results=None):
    """Membuat pesan notifikasi yang informatif berdasarkan analisis dan tindakan"""
    # Dapatkan hostname dan alamat IP server
    try:
        hostname_cmd = "hostname"
        hostname = os.popen(hostname_cmd).read().strip()
        
        ip_cmd = "hostname -I | awk '{print $1}'"
        ip_address = os.popen(ip_cmd).read().strip()
    except Exception as e:
        hostname = "unknown"
        ip_address = "unknown"
        logging.error(f"Error mendapatkan hostname/IP: {str(e)}")
    
    # Format judul dan waktu
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"<b>⚠️ MONITORING SERVER ALERT ⚠️</b>\n"
    message += f"<b>Server:</b> {hostname} ({ip_address})\n"
    message += f"<b>Waktu:</b> {current_time}\n\n"
    
    # Status dan ringkasan
    status_emoji = "🔴" if analysis["status"] == "critical" else "🟠" if analysis["status"] == "warning" else "🟢"
    message += f"<b>Status:</b> {status_emoji} {analysis['status'].upper()}\n"
    message += f"<b>Analisis:</b> {analysis['analysis']}\n\n"
    
    # Masalah yang terdeteksi
    message += "<b>🔍 Masalah Terdeteksi:</b>\n"
    for issue in analysis.get("issues", []):
        severity_emoji = "🔴" if issue["severity"] == "high" else "🟠" if issue["severity"] == "medium" else "🟡"
        message += f"{severity_emoji} <b>{issue['component'].upper()}:</b> {issue['description']}\n"
    
    message += "\n"
    
    # Tindakan yang diambil (jika ada)
    if execution_results:
        message += "<b>🛠️ Tindakan Otomatis yang Diambil:</b>\n"
        for action in execution_results:
            result = action["result"]
            if "status" in result:
                status_icon = "✅" if result["status"] in ["success", "completed"] else "❌"
                message += f"{status_icon} {action['description']}\n"
                
                # Detail tambahan untuk pembersihan disk
                if "disk_usage_after" in result:
                    message += f"   └ Penggunaan disk sekarang: {result['disk_usage_after']}\n"
                
                # Detail untuk restart service
                if "service" in result:
                    message += f"   └ Layanan: {result['service']}\n"
    else:
        message += "<b>🤖 Status:</b> Monitoring aktif, tidak ada tindakan otomatis yang diambil.\n"
    
    # Rekomendasi tambahan
    message += "\n<b>📋 Rekomendasi:</b>\n"
    for rec in analysis.get("recommendations", [])[:2]:  # Batasi hanya 2 rekomendasi teratas
        if rec.get("action") != "restart_service" or not execution_results:  # Hindari duplikasi dengan tindakan yang sudah diambil
            message += f"• {rec['description']}\n"
    
    # Tambahkan footer
    message += f"\n<i>Pesan ini dikirim otomatis oleh Server AI Monitoring System</i>"
    
    return message       

def execute_ansible_task(task_yaml):
    """Menjalankan task Ansible dari rekomendasi"""
    try:
        # Buat direktori untuk data Ansible
        ansible_dir = './ansible'
        os.makedirs(ansible_dir, exist_ok=True)
        
        # Periksa apakah ada placeholder dalam task
        if '<service_name>' in task_yaml:
            service_name = identify_high_resource_service()
            task_yaml = task_yaml.replace('<service_name>', service_name)
            logging.info(f"Mengganti placeholder dengan layanan: {service_name}")
        
        # Tulis task ke file playbook temporary dengan format yang benar
        try:
            # Load task sebagai YAML
            task_dict = yaml.safe_load(task_yaml)
            
            # Buat playbook lengkap
            playbook_content = [{
                "name": "Auto-remediation Playbook",
                "hosts": "localhost",
                "become": True,  # Tambahkan ini untuk hak akses sudo
                "tasks": [task_dict]
            }]
            
            # Simpan ke file
            playbook_file = os.path.join(ansible_dir, "auto_remediation.yml")
            with open(playbook_file, "w") as f:
                yaml.dump(playbook_content, f)
                
            logging.info(f"Playbook Ansible disimpan di: {playbook_file}")
            logging.info(f"Konten playbook: {yaml.dump(playbook_content)}")
            
            # Jalankan ansible-playbook langsung dengan os.system untuk debugging
            cmd = f"ansible-playbook -v {playbook_file}"
            return_code = os.system(cmd)
            
            if return_code != 0:
                logging.error(f"Ansible command failed with return code {return_code}")
                
            # Tetap gunakan ansible_runner untuk hasil terstruktur
            result = ansible_runner.run(
                playbook=playbook_file,
                private_data_dir=ansible_dir,
                verbosity=2  # Tingkatkan verbosity untuk debugging
            )
            
            return {
                "status": result.status,
                "rc": result.rc,
                "stats": result.stats,
                "direct_cmd_rc": return_code
            }
            
        except yaml.YAMLError as ye:
            logging.error(f"Error parsing YAML task: {ye}")
            # Fallback: simpan task sebagai string
            task_str = task_yaml.strip()
            logging.info(f"Using raw task string: {task_str}")
            
            # Membuat file playbook manual
            playbook_content = f"""---
- name: Auto-remediation Fallback
  hosts: localhost
  become: yes
  tasks:
{task_str}
"""
            playbook_file = os.path.join(ansible_dir, "auto_remediation_fallback.yml")
            with open(playbook_file, "w") as f:
                f.write(playbook_content)
                
            cmd = f"ansible-playbook -v {playbook_file}"
            return_code = os.system(cmd)
            
            return {
                "status": "manual_fallback",
                "rc": return_code,
                "command": cmd
            }
            
    except Exception as e:
        logging.error(f"Error saat menjalankan Ansible task: {str(e)}")
        return {"status": "failed", "error": str(e)}

def execute_direct_command(recommendation):
    """Eksekusi langsung untuk restart service atau kill proses"""
    try:
        # Identifikasi proses bermasalah
        target = identify_high_resource_service()
        
        if not target:
            logging.warning("Tidak dapat mengidentifikasi target untuk tindakan")
            return {"status": "failed", "error": "Tidak dapat mengidentifikasi target"}
        
        # Handle proses khusus yang bukan service
        if target.startswith("process:"):
            pid = target.split(':')[1]
            logging.info(f"Menangani proses dengan PID {pid}")
            
            # Cek informasi proses
            cmd_info = f"ps -p {pid} -o cmd=,%cpu=,%mem="
            process_info = os.popen(cmd_info).read().strip()
            
            # Coba kill dengan sinyal TERM (15)
            kill_cmd = f"kill -15 {pid}"
            import subprocess
            result = subprocess.run(kill_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                logging.info(f"Berhasil mengirim SIGTERM ke proses {pid}: {process_info}")
                return {
                    "status": "success", 
                    "action": "kill_process",
                    "pid": pid,
                    "info": process_info
                }
            else:
                logging.error(f"Gagal mengirim SIGTERM ke proses {pid}: {result.stderr}")
                return {"status": "failed", "error": result.stderr}
        
        # Handle service restart
        service_name = target
        
        # Cek apakah ini layanan kritis
        critical_services = ['systemd', 'sshd', 'kernel', 'init']
        if service_name.lower() in critical_services:
            logging.warning(f"Menghindari restart layanan kritis: {service_name}")
            return {"status": "skipped", "reason": "critical service"}
        
        # Uji apakah layanan ada
        check_cmd = f"systemctl status {service_name} 2>&1"
        check_result = os.popen(check_cmd).read()
        
        if "could not be found" in check_result or "no such service" in check_result.lower():
            logging.warning(f"Layanan {service_name} tidak ditemukan")
            return {"status": "failed", "error": f"Service {service_name} not found"}
        
        # Jalankan restart service
        logging.info(f"Mencoba me-restart layanan: {service_name}")
        
        # Gunakan pendekatan yang lebih aman dengan subprocess
        import subprocess
        try:
            # Mencoba dengan sudo
            restart_cmd = ["sudo", "systemctl", "restart", service_name]
            result = subprocess.run(restart_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                logging.info(f"Berhasil me-restart layanan: {service_name}")
                return {"status": "success", "service": service_name, "output": result.stdout}
            else:
                logging.error(f"Gagal me-restart {service_name}: {result.stderr}")
                return {"status": "failed", "service": service_name, "error": result.stderr}
                
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout saat me-restart {service_name}")
            return {"status": "timeout", "service": service_name}
            
    except Exception as e:
        logging.error(f"Error saat menjalankan command: {str(e)}")
        return {"status": "failed", "error": str(e)}

def clean_disk_space():
    """Membersihkan ruang disk secara agresif"""
    try:
        logging.info("Melakukan pembersihan disk")
        
        # Lokasi pembersihan
        cleanup_commands = [
            "sudo apt-get clean",
            "sudo apt-get autoremove -y",
            "sudo rm -rf /var/log/*.gz /var/log/*.1 /var/log/*.2 /var/log/*.old",
            "sudo find /var/log -type f -name '*.log' -exec truncate -s 0 {} \\;",
            "sudo rm -rf /tmp/* /var/tmp/*",
            "sudo journalctl --vacuum-time=1d",
            "sudo find /var/cache -type f -delete"
        ]
        
        results = []
        for cmd in cleanup_commands:
            logging.info(f"Menjalankan: {cmd}")
            exit_code = os.system(cmd)
            results.append({
                "command": cmd,
                "success": exit_code == 0
            })
        
        # Cek ruang disk setelah pembersihan
        disk_cmd = "df -h / | tail -1 | awk '{print $5}'"
        disk_usage_after = os.popen(disk_cmd).read().strip()
        
        return {
            "status": "completed",
            "disk_usage_after": disk_usage_after,
            "commands": results
        }
    except Exception as e:
        logging.error(f"Error saat membersihkan disk: {str(e)}")
        return {"status": "failed", "error": str(e)}

def save_report(analysis):
    """Menyimpan hasil analisis ke file"""
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{reports_dir}/report_{timestamp}.json"
    
    with open(filename, "w") as f:
        json.dump(analysis, f, indent=2)
    
    return filename

def is_safe_task(task_yaml, service_name):
    """Memeriksa apakah task aman untuk dijalankan"""
    # Daftar layanan kritis yang tidak boleh direstart otomatis
    critical_services = ['mysql', 'nginx', 'apache2', 'postgresql', 'docker']
    
    if service_name in critical_services:
        logging.warning(f"Menghindari restart otomatis layanan kritis: {service_name}")
        return False
        
    # Tambahkan validasi lain sesuai kebutuhan
    
    return True

def find_and_handle_resource_hogs():
    """Menemukan dan menangani proses yang memakan terlalu banyak CPU"""
    try:
        # Dapatkan proses dengan CPU tertinggi
        cmd = "ps -eo pid,%cpu,user,cmd --sort=-%cpu | head -3 | tail -2"
        top_processes = os.popen(cmd).read().strip().split('\n')
        
        results = []
        for process in top_processes:
            parts = process.split()
            if len(parts) >= 4:
                pid = parts[0]
                cpu_usage = float(parts[1])
                user = parts[2]
                cmd_name = ' '.join(parts[3:])
                
                # Jika penggunaan CPU sangat tinggi (> 80%)
                if cpu_usage > 80:
                    logging.warning(f"Proses dengan CPU sangat tinggi terdeteksi: PID {pid}, CPU {cpu_usage}%, Command: {cmd_name}")
                    
                    # Periksa apakah ini proses sistem kritis
                    safe_to_kill = True
                    critical_processes = ['systemd', 'init', 'sshd', 'bash', 'python3']
                    
                    for critical in critical_processes:
                        if critical in cmd_name.lower():
                            safe_to_kill = False
                            break
                    
                    if safe_to_kill and user != "root":
                        # Coba hentikan proses dengan SIGTERM
                        logging.info(f"Mencoba menghentikan proses: {pid}")
                        kill_result = os.system(f"kill -15 {pid}")
                        
                        results.append({
                            "pid": pid,
                            "cpu": cpu_usage,
                            "command": cmd_name,
                            "action": "terminated",
                            "result": "success" if kill_result == 0 else "failed"
                        })
                    else:
                        results.append({
                            "pid": pid,
                            "cpu": cpu_usage,
                            "command": cmd_name,
                            "action": "skipped",
                            "reason": "critical process or root"
                        })
        
        return results
    except Exception as e:
        logging.error(f"Error saat menangani proses CPU tinggi: {str(e)}")
        return []

def send_daily_summary():
    """Mengirim ringkasan harian status server"""
    try:
        # Dapatkan informasi CPU, memory, dan disk
        cpu_cmd = "top -bn1 | grep 'Cpu(s)' | awk '{print $2 + $4}'"
        cpu_usage = os.popen(cpu_cmd).read().strip()
        
        mem_cmd = "free -m | grep Mem | awk '{print $3/$2 * 100.0}'"
        mem_usage = os.popen(mem_cmd).read().strip()
        
        disk_cmd = "df -h / | tail -1 | awk '{print $5}'"
        disk_usage = os.popen(disk_cmd).read().strip()
        
        uptime_cmd = "uptime -p"
        uptime = os.popen(uptime_cmd).read().strip()
        
        # Format message
        message = "<b>📊 LAPORAN STATUS SERVER HARIAN 📊</b>\n\n"
        message += f"<b>Waktu:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        message += f"<b>Uptime:</b> {uptime}\n\n"
        
        message += "<b>Penggunaan Sumber Daya:</b>\n"
        message += f"🔸 CPU: {cpu_usage}%\n"
        message += f"🔸 Memori: {mem_usage}%\n"
        message += f"🔸 Disk: {disk_usage}\n\n"
        
        # Baca laporan terbaru
        reports_dir = "reports"
        reports = []
        
        if os.path.exists(reports_dir):
            for file in sorted(os.listdir(reports_dir), reverse=True):
                if file.startswith("report_") and file.endswith(".json"):
                    try:
                        with open(os.path.join(reports_dir, file), 'r') as f:
                            report_data = json.load(f)
                            reports.append({
                                'file': file,
                                'status': report_data.get('status', 'unknown'),
                                'timestamp': file.split('_')[1].split('.')[0]
                            })
                    except Exception as e:
                        logging.error(f"Error membaca file laporan {file}: {str(e)}")
                        
                    # Hanya baca 5 file terbaru
                    if len(reports) >= 5:
                        break
        
        if reports:
            message += "<b>Laporan Terbaru:</b>\n"
            for i, report in enumerate(reports):
                status_emoji = "🔴" if report["status"] == "critical" else "🟠" if report["status"] == "warning" else "🟢"
                timestamp = datetime.strptime(report["timestamp"], "%Y%m%d_%H%M%S").strftime("%d/%m %H:%M")
                message += f"{i+1}. {status_emoji} {timestamp} - {report['status'].upper()}\n"
        else:
            message += "<b>Tidak ada laporan terbaru.</b>\n"
            
        message += "\n<i>Laporan ini dikirim otomatis oleh Server AI Monitoring System</i>"
        
        # Kirim ke Telegram
        return send_telegram_notification(message)
    
    except Exception as e:
        logging.error(f"Error saat membuat ringkasan harian: {str(e)}")
        return {"status": "failed", "error": str(e)}
        

def main():
    """Fungsi utama yang menjalankan workflow otomatisasi"""
    logging.info("Memulai proses otomatisasi server")
    
    # Ambil metrik dari Prometheus
    metrics = get_prometheus_metrics()
    if not metrics:
        logging.error("Gagal mendapatkan metrik. Menghentikan proses.")
        return
    
    # Analisis dengan Gemini AI
    analysis = analyze_with_gemini(metrics)
    
    # Simpan laporan
    report_file = save_report(analysis)
    logging.info(f"Laporan analisis disimpan di {report_file}")
    
    execution_results = []
    
    # Cek masalah disk
    disk_issue = next((issue for issue in analysis.get("issues", []) 
                     if issue.get("component") == "disk" and issue.get("severity") == "high"), None)
    
    if disk_issue:
        logging.warning("Terdeteksi masalah disk usage tinggi! Menjalankan pembersihan disk...")
        disk_result = clean_disk_space()
        logging.info(f"Hasil pembersihan disk: {disk_result}")
        execution_results.append({
            "description": "Pembersihan disk otomatis",
            "result": disk_result
        })
    
    # Cek status dan jalankan rekomendasi jika perlu
    if analysis["status"] == "critical":
        logging.warning("Terdeteksi masalah CRITICAL! Menjalankan rekomendasi otomatis...")
        
        for rec in analysis.get("recommendations", []):
            if rec.get("action") == "restart_service":
                logging.info(f"Menjalankan tugas: {rec['description']}")
                
                # Langsung gunakan direct command (skip Ansible)
                result = execute_direct_command(rec)
                logging.info(f"Hasil eksekusi direct: {result}")
                
                execution_results.append({
                    "description": rec["description"],
                    "result": result
                })
        
        # Simpan hasil eksekusi
        if execution_results:
            results_dir = "reports"
            os.makedirs(results_dir, exist_ok=True)
            results_file = f"{results_dir}/execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(results_file, "w") as f:
                json.dump(execution_results, f, indent=2)
            logging.info(f"Hasil eksekusi disimpan di {results_file}")
                
    # Kirim notifikasi ke Telegram
    if analysis["status"] in ["critical", "warning"]:
        # Format pesan notifikasi
        message = format_notification_message(analysis, execution_results if execution_results else None)
        
        # Kirim notifikasi
        logging.info("Mengirim notifikasi ke Telegram...")
        telegram_result = send_telegram_notification(message)
        logging.info(f"Hasil pengiriman notifikasi: {telegram_result}")
        
    elif analysis["status"] == "warning":
        logging.info("Terdeteksi WARNING. Menyimpan rekomendasi untuk review.")
        
    else:
        logging.info("Server dalam kondisi baik. Tidak ada tindakan yang diperlukan.")
        
if __name__ == "__main__":
    main()
