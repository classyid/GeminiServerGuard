# GeminiServerGuard 🛡️🤖

![Screenshoot](https://blog.classy.id/upload/gambar_berita/7a625a78a6058f7074406b7ba24e7644_20250417153117.jpg)

GeminiServerGuard adalah sistem monitoring server otomatis yang menggunakan kecerdasan buatan Google Gemini untuk menganalisis metrik server, mendeteksi masalah, dan melakukan tindakan perbaikan secara otomatis. Sistem ini terintegrasi dengan Prometheus untuk pengumpulan metrik dan Telegram untuk notifikasi real-time.

## ✨ Fitur

- 📊 **Monitoring Metrik Utama**: CPU, memori, disk usage, load average, dan jaringan
- 🧠 **Analisis AI**: Menggunakan Google Gemini untuk menganalisis dan mendiagnosis masalah server
- 🛠️ **Tindakan Otomatis**: Pembersihan disk, restart layanan, dan identifikasi proses bermasalah
- 📱 **Notifikasi Telegram**: Pemberitahuan real-time dengan informasi lengkap tentang masalah dan tindakan
- 📝 **Pelaporan**: Menyimpan laporan analisis dan eksekusi untuk audit dan analisis historis
- 🔍 **Identifikasi Cerdas**: Menghindari sistem kritis dan hanya melakukan tindakan pada layanan yang aman

## 🔧 Instalasi

### Prasyarat

- Python 3.8+
- Prometheus (dan Node Exporter)
- Bot Telegram (untuk notifikasi)

### Langkah Instalasi

1. Kloning repositori ini:
   ```bash
   git clone https://github.com/classyid/GeminiServerGuard.git
   cd GeminiServerGuard
   ```

2. Buat dan aktifkan virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Di Windows: venv\Scripts\activate
   ```

3. Instal dependensi:
   ```bash
   pip install google-generativeai requests pyyaml ansible-runner
   ```

4. Perbarui file konfigurasi:
   ```bash
   cp config.example.yml config.yml
   # Edit config.yml dengan API key Gemini, token Telegram, dll.
   ```

5. Jalankan untuk pertama kali:
   ```bash
   python server_automation.py
   ```

## ⚙️ Konfigurasi

Edit file `config.yml` untuk menyesuaikan:

- API key Google Gemini
- URL Prometheus
- Token dan chat ID Telegram
- Layanan kritis yang tidak boleh di-restart
- Threshold untuk tindakan otomatis
- Jadwal ringkasan harian

## 📊 Metrik yang Dipantau

- **CPU Usage**: Penggunaan CPU dalam persentase
- **Memory Usage**: Penggunaan memori dalam persentase
- **Disk Usage**: Penggunaan disk dalam persentase
- **Load Average**: Beban rata-rata sistem
- **Network Traffic**: Lalu lintas jaringan masuk dan keluar

## 🔔 Notifikasi Telegram

Notifikasi yang dikirim melalui Telegram mencakup:

- Status server (kritis, peringatan, sehat)
- Analisis detail masalah yang terdeteksi
- Tindakan otomatis yang telah diambil
- Rekomendasi untuk administrator
- Hostname dan alamat IP server

## 🕒 Otomatisasi

Untuk menjalankan pemantauan secara berkala, tambahkan ke crontab:

```bash
# Jalankan setiap 15 menit
*/15 * * * * cd /path/to/GeminiServerGuard && ./venv/bin/python server_automation.py >> cron.log 2>&1

# Kirim laporan ringkasan harian pada jam 8 pagi
0 8 * * * cd /path/to/GeminiServerGuard && ./venv/bin/python server_automation.py --daily-summary >> summary.log 2>&1
```

## 🔐 Keamanan

GeminiServerGuard dirancang dengan keamanan sebagai prioritas:

- Tidak pernah me-restart layanan sistem kritis
- Memvalidasi tindakan sebelum eksekusi
- Hanya mengirimkan notifikasi ke chat ID Telegram yang ditentukan
- Menyimpan log tindakan untuk audit

## 📋 Lisensi

Proyek ini dilisensikan di bawah MIT License - lihat file [LICENSE](LICENSE) untuk detail.

## 🙏 Ucapan Terima Kasih

- [Google Gemini API](https://ai.google.dev/) untuk analisis AI
- [Prometheus](https://prometheus.io/) untuk pengumpulan metrik
- Semua kontributor dan pengguna proyek ini

## 📞 Kontak

Jika Anda memiliki pertanyaan atau saran, silakan buka issue di GitHub atau hubungi kami melalui email di kontak@classy.id
