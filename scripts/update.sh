#!/bin/sh
# Pull the latest changes and bring the local environment back in sync.
#   $ ./scripts/update.sh
# Safe to run any time: each step is a no-op when nothing changed.
set -eu

cd "$(dirname "$0")/.."

echo
echo "[1/4] Yerel değişiklikler kontrol ediliyor..."
# Only tracked edits can collide with a pull; new files of your own are fine.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "Takip edilen dosyalarda kaydedilmemiş değişiklik var:"
    git status --short --untracked-files=no
    if [ -t 0 ]; then
        printf "\nDevam edilsin mi? 'git pull' çakışma verebilir. (e/h) "
        read -r answer
        [ "$answer" = "e" ] || { echo "İptal edildi."; exit 1; }
    else
        echo "Etkileşimsiz çalışıyor; devam ediliyor."
    fi
fi

echo
echo "[2/4] GitHub'dan son sürüm çekiliyor..."
git pull

PYTHON=python3
[ -x ".venv/bin/python" ] && PYTHON=".venv/bin/python"

echo
echo "[3/4] Bağımlılıklar kontrol ediliyor..."
"$PYTHON" -m pip install --quiet -r requirements.txt

echo
echo "[4/4] Veritabanı güncelleniyor..."
"$PYTHON" manage.py migrate

echo
echo "Hazır. Sunucuyu başlatmak için:"
echo "  $PYTHON manage.py runserver"
echo
