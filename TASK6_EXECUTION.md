# Task 6 Execution Guide (Testing + Polish)

Dokumen ini dipakai saat implementasi dan verifikasi Task 6.

## 1) Persiapan

- Install dependency: `pip install -r requirements.txt`
- Isi file `.env`
- Jalankan bot: `python main.py`

## 2) Skenario Uji Utama

1. Tunggu bot kirim `/next`
2. Saat match masuk, pastikan bot kirim `hii` lalu `m f?`
3. Kirim `co` atau `m` dari akun lawan
4. Pastikan bot skip dan kirim `/next` lagi
5. Match lagi, kirim `ce` atau `f`
6. Pastikan bot masuk mode chatting dan balas otomatis

## 3) Uji Auto-Reply

- Kirim 3-5 pesan normal dari akun lawan
- Pastikan bot balas setiap pesan
- Jika respons model berisi beberapa baris, pastikan terkirim terpisah per bubble

## 4) Uji Disconnect

- Putuskan chat dari akun lawan
- Pastikan log menunjukkan disconnect terdeteksi
- Pastikan bot reset session dan kirim `/next`

## 5) Tuning Delay

- Jika terlalu cepat: naikkan `TYPING_DELAY_MIN`, `TYPING_DELAY_MAX`
- Jika terlalu lambat: turunkan nilainya
- Untuk jeda antar bubble, atur `BUBBLE_DELAY_MIN`, `BUBBLE_DELAY_MAX`

## 6) Validasi Akhir

- Jalankan siklus lengkap minimal 3 kali
- Pastikan tidak crash
- Pastikan state selalu kembali normal setelah disconnect

## 7) Definisi Done

- Semua skenario utama lolos
- Recovery setelah disconnect stabil
- Delay sudah terasa natural
- Log cukup jelas untuk troubleshooting
