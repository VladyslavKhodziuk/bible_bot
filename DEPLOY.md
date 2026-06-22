# Деплой и поддержка

Прод-сетап: Hetzner Cloud VPS + Ubuntu 24.04 + systemd. Бот работает на
long-polling, поэтому **публичный IP/домен/HTTPS не нужны** — достаточно
исходящего интернета.

---

## 0. Pre-flight чек-лист

Сделай это **до** того, как пойдёшь на сервер:

- [ ] **Новый прод-бот в @BotFather**: `/newbot` → имя → username → токен.
      Менять токен у dev-бота нельзя — long-polling от двух процессов с одним
      токеном даст 409 Conflict.
- [ ] **Записан токен** (`BOT_TOKEN`) и список своих admin user_id (`ADMIN_IDS`,
      узнать у @userinfobot).
- [ ] **Gemini API key**: https://aistudio.google.com/apikey → `GEMINI_API_KEY`.
- [ ] **Фидбэк-группы** (опционально, можно позже): 1–3 группы в Telegram,
      бот добавлен админом. `chat_id` получишь через бота: ЛС → переслать
      сообщение из группы → `/chatid`.
- [ ] **Hetzner аккаунт** + SSH-ключ в Hetzner Cloud Console.

---

## 1. Создание сервера

В Hetzner Cloud Console:

- **Project** → New project (например, `bible-bot`).
- **Add Server**:
  - Location: ближайший (Falkenstein/Nuremberg/Helsinki).
  - Image: **Ubuntu 24.04**.
  - Type: **CX22** (€4.50/мес, 2 vCPU / 4 GB RAM) — с запасом. CX11 уже снят.
  - Networking: IPv4 + IPv6.
  - SSH keys: выбрать свой.
  - Name: `bible-bot-prod`.
- Создать → запомнить **IPv4**.

---

## 2. Первичная настройка сервера

С локальной машины:

```bash
ssh root@<IP>
```

На сервере (под root):

```bash
# Обновляем систему
apt update && apt upgrade -y

# Базовые пакеты
apt install -y python3.12 python3.12-venv python3-pip git sqlite3 ufw

# Файервол: только SSH наружу открыт
ufw allow OpenSSH
ufw enable
ufw status

# Юзер для бота (без sudo)
useradd -m -s /bin/bash bible

# Перекинуть свой SSH-ключ юзеру bible, чтобы заходить напрямую
mkdir -p /home/bible/.ssh
cp /root/.ssh/authorized_keys /home/bible/.ssh/
chown -R bible:bible /home/bible/.ssh
chmod 700 /home/bible/.ssh
chmod 600 /home/bible/.ssh/authorized_keys
```

Выходим и заходим уже юзером `bible`:

```bash
exit
ssh bible@<IP>
```

---

## 3. Клонирование и установка

Под юзером `bible`:

```bash
cd ~
git clone https://github.com/VladyslavKhodziuk/bible_bot.git
cd bible_bot

# Виртуальное окружение
python3.12 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Создаём .env из шаблона
cp .env.example .env
nano .env   # заполнить BOT_TOKEN, GEMINI_API_KEY, ADMIN_IDS, остальное по вкусу
chmod 600 .env   # никто кроме bible не должен читать
```

Быстрый тест запуска (Ctrl+C через 5 сек):

```bash
./venv/bin/python main.py
```

Должно вывести `База данных готова → Библии загружены → Планировщик запущен → Run polling for bot @<your_prod_bot>`. Базы (`bot.db`) создастся сама.

---

## 4. systemd-сервис

Под `bible`:

```bash
sudo cp ~/bible_bot/deploy/bible-bot.service /etc/systemd/system/bible-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now bible-bot
sudo systemctl status bible-bot
```

(Установить sudo для `bible` отдельно или делать `sudo` под root'ом — на твой
выбор. Минимально: разреши `bible` только `systemctl start/stop/restart/status
bible-bot` через `/etc/sudoers.d/bible-bot`.)

Логи:

```bash
journalctl -u bible-bot -f          # live tail
journalctl -u bible-bot --since "1 hour ago"
journalctl -u bible-bot -p err      # только ошибки
```

Проверка в Telegram: пиши `/start` своему прод-боту → должен ответить.

---

## 5. Бэкапы

Под `bible`:

```bash
mkdir -p ~/backups
chmod +x ~/bible_bot/deploy/backup.sh
# Прогон вручную для проверки
~/bible_bot/deploy/backup.sh
ls -lh ~/backups/

# Ставим в cron: каждый день в 03:00
( crontab -l 2>/dev/null; echo "0 3 * * * /home/bible/bible_bot/deploy/backup.sh >> /home/bible/backups/backup.log 2>&1" ) | crontab -
crontab -l
```

**Дополнительно (рекомендую):** копировать бэкапы наружу — иначе при потере
сервера потеряешь и базу. Варианты: Hetzner Storage Box, rclone в любой S3,
scp на свою машину. Минимум — раз в неделю.

---

## 6. Выкатка обновлений

С локальной машины:

```bash
git push origin main
```

На сервере под `bible`:

```bash
cd ~/bible_bot
git pull origin main
# Если в этом релизе менялись зависимости:
./venv/bin/pip install -r requirements.txt
sudo systemctl restart bible-bot
journalctl -u bible-bot -n 50
```

`drop_pending_updates=True` уже стоит в `main.py` — пара секунд простоя на
рестарте не приведут к «лавине» накопившихся апдейтов.

### Когда нужен `pip install`

Только если изменились версии в `requirements.txt`. Можно проверить заранее:

```bash
git diff HEAD@{1} HEAD -- requirements.txt
```

---

## 7. Откат

Если новый релиз сломал прод:

```bash
cd ~/bible_bot
git log --oneline -10            # найти хэш предыдущего рабочего коммита
git reset --hard <HASH>          # откатить локально (на сервере)
./venv/bin/pip install -r requirements.txt   # если меняли deps
sudo systemctl restart bible-bot
```

Если сломалась БД — восстановить из бэкапа:

```bash
sudo systemctl stop bible-bot
gunzip -c ~/backups/bot-2026-06-22_0300.db.gz > ~/bible_bot/bot.db
# Удалить WAL/SHM от старого процесса (если есть)
rm -f ~/bible_bot/bot.db-wal ~/bible_bot/bot.db-shm
sudo systemctl start bible-bot
```

---

## 8. Обновление зависимостей

Когда хочешь обновить версию пакета:

```bash
# Локально, в dev-окружении:
.\venv\Scripts\Activate.ps1            # Windows; на Linux: source venv/bin/activate
pip install -U aiogram                 # пример: обновляем aiogram
pip freeze > /tmp/freeze.txt
# Обновить прямую версию в requirements.txt вручную, потом пересобрать lock-секцию
# по /tmp/freeze.txt. Запустить бота, прогнать сценарии.
git commit + git push
# На сервере — обычный pull + pip install + restart (шаг 6).
```

---

## 9. Поддержка — что мониторить

| Что | Где | Действие |
|---|---|---|
| Алерты о сбоях | ЛС у `ADMIN_IDS` | приходят автоматически |
| Daily report | `REPORT_CHAT_ID` или ЛС | в `REPORT_TIME` каждый день |
| Monthly report | то же | `MONTHLY_REPORT_DAY` |
| Резкое падение трафика | daily report | проверить `journalctl -u bible-bot -p err` |
| Размер `bot.db` | `du -h ~/bible_bot/bot.db` | SQLite спокойно держит сотни тыс. юзеров |
| Свободное место | `df -h /` | алерт сработает при ≥90% |
| Бэкапы | `ls -lh ~/backups/` | свежий за сегодня должен быть |

---

## 10. Полезные команды

```bash
# Статус и управление
sudo systemctl status bible-bot
sudo systemctl restart bible-bot
sudo systemctl stop bible-bot

# Логи
journalctl -u bible-bot -f
journalctl -u bible-bot --since today
journalctl -u bible-bot -p warning..err

# Быстрый SQL-просмотр
sqlite3 ~/bible_bot/bot.db "SELECT COUNT(*) FROM users;"
sqlite3 ~/bible_bot/bot.db "SELECT date_hour, total_events FROM activity_hourly ORDER BY id DESC LIMIT 24;"

# Использование ресурсов
htop
free -h
df -h
```

---

## FAQ

**Я случайно запустил dev-бота и прод одновременно — что будет?**
У них разные токены — ничего страшного, оба работают независимо. Один токен
запускать дважды нельзя (409 Conflict).

**Можно ли мигрировать `bot.db` с dev на prod?**
Технически да (`scp`), но не рекомендую: dev-БД содержит твоих тестовых
юзеров, фейковую статистику и тестовые подписки на уведомления. Чище
стартовать прод с пустой базой — `init_db()` создаст схему сама.

**Что делать со сломанной миграцией?**
Миграции в `database.py::run_migrations()` идемпотентны и записывают ключ в
`migrations_applied.txt`. Если новая миграция упала на проде: исправить блок,
запушить, на сервере удалить её ключ из `migrations_applied.txt`, рестарт.
