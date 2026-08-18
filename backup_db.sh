#!/usr/bin/env bash
# ==============================================================================
# Food Price Pipeline - PostgreSQL Docker Backup & Restore Manager
# ==============================================================================
# Description:
#   Script untuk melakukan backup berkala database PostgreSQL dari Docker
#   ke komputer lokal dalam format .sql.gz, restorasi database, dan pembersihan
#   retensi otomatis (30 hari).
#
# Jadwal Cron: Setiap Jumat pukul 23.00 WIB (0 23 * * 5)
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
BACKUP_DIR="${PROJECT_ROOT}/backups"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/backup.log"

# --- Konfigurasi Default ---
DOCKER_CONTAINER="foodprice_postgres"
DB_USER="foodprice_admin"
DB_NAME="foodprice_dw"
DB_PASS=""

# Muat variabel dari .env jika tersedia
if [ -f "${PROJECT_ROOT}/.env" ]; then
  ENV_USER=$(grep -E "^POSTGRES_USER=" "${PROJECT_ROOT}/.env" | cut -d '=' -f2- | tr -d '"' | tr -d "'" || true)
  ENV_PASS=$(grep -E "^POSTGRES_PASSWORD=" "${PROJECT_ROOT}/.env" | cut -d '=' -f2- | tr -d '"' | tr -d "'" || true)
  ENV_DB=$(grep -E "^POSTGRES_DB=" "${PROJECT_ROOT}/.env" | cut -d '=' -f2- | tr -d '"' | tr -d "'" || true)
  
  [ -n "$ENV_USER" ] && DB_USER="$ENV_USER"
  [ -n "$ENV_PASS" ] && DB_PASS="$ENV_PASS"
  [ -n "$ENV_DB" ] && DB_NAME="$ENV_DB"
fi

mkdir -p "${BACKUP_DIR}"
mkdir -p "${LOG_DIR}"

# --- Utility Output Functions ---
color_cyan()   { echo -e "\033[0;36m$*\033[0m"; }
color_green()  { echo -e "\033[0;32m$*\033[0m"; }
color_yellow() { echo -e "\033[0;33m$*\033[0m"; }
color_red()    { echo -e "\033[0;31m$*\033[0m"; }

log_message() {
  local timestamp
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[${timestamp}] $*" | tee -a "${LOG_FILE}"
}

check_docker_db() {
  if ! docker ps --format '{{.Names}}' | grep -q "^${DOCKER_CONTAINER}$"; then
    color_red "❌ Container '${DOCKER_CONTAINER}' tidak sedang berjalan / OFFLINE!"
    return 1
  fi

  # Verifikasi apakah PostgreSQL di dalam container siap menerima query
  if ! docker exec -e PGPASSWORD="${DB_PASS}" "${DOCKER_CONTAINER}" pg_isready -U "${DB_USER}" -d "${DB_NAME}" >/dev/null 2>&1; then
    color_red "❌ PostgreSQL di dalam container '${DOCKER_CONTAINER}' belum siap menerima koneksi!"
    return 1
  fi
  return 0
}

# --- Actions ---
do_status() {
  color_cyan "========================================================"
  color_cyan "     Food Price DW - Database Backup & Container Status "
  color_cyan "========================================================"
  echo ""
  
  echo -n "🐳 Docker Container (${DOCKER_CONTAINER}): "
  if check_docker_db >/dev/null 2>&1; then
    color_green "ONLINE"
    echo "   Database : ${DB_NAME} | User: ${DB_USER}"
  else
    color_red "OFFLINE"
    echo "   Pastikan container berjalan dengan: docker compose -f docker/docker-compose.yml up -d"
  fi

  echo ""
  echo "📦 Backup Tersimpan di ${BACKUP_DIR}:"
  local count
  count=$(find "${BACKUP_DIR}" -maxdepth 1 -name "*.sql.gz" -o -name "*.sql" 2>/dev/null | wc -l)
  if [ "${count}" -eq 0 ]; then
    echo "   (Belum ada file backup)"
  else
    ls -lh "${BACKUP_DIR}" | grep -E '\.sql' | awk '{print "   • " $9 " (" $5 ", modifikasi: " $6 " " $7 " " $8 ")"}'
  fi
  echo ""
  echo "📋 File Log: ${LOG_FILE}"
  echo ""
}

do_backup() {
  if ! check_docker_db; then
    log_message "[ERROR] Backup GAGAL: Container ${DOCKER_CONTAINER} offline atau database belum siap."
    return 1
  fi

  local TIMESTAMP
  TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
  local BACKUP_FILE="${BACKUP_DIR}/foodprice_backup_${TIMESTAMP}.sql.gz"

  color_cyan "📦 Membuat snapshot backup database dari Docker (${DOCKER_CONTAINER})..."
  
  # Eksekusi pg_dump via docker exec lalu pipe ke gzip
  if docker exec -e PGPASSWORD="${DB_PASS}" "${DOCKER_CONTAINER}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" --clean --if-exists | gzip > "${BACKUP_FILE}"; then
    local SIZE
    SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    color_green "✅ Backup BERHASIL dibuat: ${BACKUP_FILE} (${SIZE})"
    log_message "[SUCCESS] Backup berhasil dibuat: ${BACKUP_FILE} (${SIZE})"
  else
    color_red "❌ Gagal membuat snapshot backup!"
    log_message "[ERROR] Gagal saat mengeksekusi pg_dump."
    # Hapus file corrupted jika ada
    [ -f "${BACKUP_FILE}" ] && rm -f "${BACKUP_FILE}"
    return 1
  fi
}

do_restore() {
  local FILE="$1"
  if [ -z "${FILE}" ] || [ ! -f "${FILE}" ]; then
    color_red "❌ File backup tidak ditemukan: ${FILE}"
    echo "Penggunaan: $0 restore <path_ke_file.sql.gz>"
    exit 1
  fi

  if ! check_docker_db; then
    color_red "❌ Tidak dapat melakukan restore karena container ${DOCKER_CONTAINER} offline."
    exit 1
  fi

  color_yellow "⚠️  PERINGATAN: Memulihkan database akan MENIMPA seluruh data pada '${DB_NAME}'!"
  read -p "Apakah Anda yakin ingin melanjutkan? (y/N): " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    color_cyan "Operasi pemulihan dibatalkan oleh pengguna."
    exit 0
  fi

  color_cyan "📥 Memulihkan data dari ${FILE} ke ${DOCKER_CONTAINER}:${DB_NAME}..."
  if [[ "${FILE}" == *.gz ]]; then
    gunzip -c "${FILE}" | docker exec -i -e PGPASSWORD="${DB_PASS}" "${DOCKER_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" >/dev/null
  else
    docker exec -i -e PGPASSWORD="${DB_PASS}" "${DOCKER_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" < "${FILE}" >/dev/null
  fi

  color_green "✅ Pemulihan database BERHASIL!"
  log_message "[SUCCESS] Database ${DB_NAME} berhasil dipulihkan dari ${FILE}"
}

do_cleanup_retention() {
  color_cyan "🧹 Membersihkan file backup yang lebih tua dari 30 hari..."
  local deleted_files
  deleted_files=$(find "${BACKUP_DIR}" -type f -name "foodprice_backup_*.sql.gz" -mtime +30 -print -delete)
  if [ -n "${deleted_files}" ]; then
    color_yellow "File backup lama yang dihapus:"
    echo "${deleted_files}"
    log_message "[INFO] Membersihkan file backup lama (>30 hari): $(echo "${deleted_files}" | tr '\n' ' ')"
  else
    echo "Tidak ada file backup yang lebih tua dari 30 hari."
  fi
}

do_auto_backup() {
  log_message "=== [START] Menjalankan Jadwal Auto Backup & Cleanup ==="
  if do_backup; then
    do_cleanup_retention
    log_message "=== [END] Auto Backup & Cleanup Selesai dengan Sukses ==="
  else
    log_message "=== [END] Auto Backup GAGAL (Lihat pesan error di atas) ==="
    exit 1
  fi
}

do_show_cron() {
  color_cyan "========================================================"
  color_cyan "   Panduan Pemasangan Cron Job (Setiap Jumat 23.00)     "
  color_cyan "========================================================"
  echo ""
  echo "Jadwal cron untuk menjalankan auto backup setiap hari Jumat pukul 23.00 WIB:"
  echo ""
  color_green "0 23 * * 5 ${PROJECT_ROOT}/backup_db.sh auto-backup >> ${LOG_FILE} 2>&1"
  echo ""
  echo "Langkah instalasi:"
  echo "1. Buka editor crontab dengan perintah:"
  echo "   crontab -e"
  echo "2. Tempelkan baris di atas pada baris paling bawah lalu simpan."
  echo "3. Cek apakah cron job sudah terdaftar:"
  echo "   crontab -l"
  echo ""
}

# --- Main Entrypoint ---
case "${1:-}" in
  status)
    do_status
    ;;
  backup)
    do_backup
    ;;
  restore)
    do_restore "$2"
    ;;
  cleanup)
    do_cleanup_retention
    ;;
  auto-backup)
    do_auto_backup
    ;;
  cron)
    do_show_cron
    ;;
  *)
    color_cyan "========================================================"
    color_cyan " Food Price DW - PostgreSQL Docker Backup Tool          "
    color_cyan "========================================================"
    echo "Penggunaan: $0 <perintah>"
    echo ""
    echo "Perintah yang tersedia:"
    echo "  $0 status                 : Cek status container database & daftar file backup"
    echo "  $0 backup                 : Buat 1 snapshot backup baru (.sql.gz) secara manual"
    echo "  $0 restore <file.sql.gz>  : Restore database dari file snapshot backup"
    echo "  $0 cleanup                : Hapus file backup yang lebih tua dari 30 hari"
    echo "  $0 auto-backup            : Buat backup dan bersihkan file lama (untuk cron job)"
    echo "  $0 cron                   : Tampilkan baris konfigurasi crontab (Jumat 23.00)"
    echo ""
    exit 0
    ;;
esac
