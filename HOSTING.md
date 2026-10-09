# Развертывание бота в облаке (работа без ПК)

Бот — обычный Python-скрипт с долгоживущим процессом. Ему нужен сервер,
который работает 24/7: `python bot.py` + переменная окружения `BOT_TOKEN`.

> Важно: с вашей текущей сети сейчас недоступен `api.telegram.org`
> (таймауты). В облаке (серверы в Европе/США) Telegram доступен —
> поэтому бот в облаке заработает, даже если локально не запускается.
> Для локального запуска используйте прокси: `PROXY_URL=...` в `.env`.

---

## Шаг 0. Подготовка: Git и GitHub

На вашем ПК **Git не установлен**. Установите:

```bat
winget install Git.Git
```

(или скачайте с https://git-scm.com/download/win — дальше «Next» до конца).
После установки **перезапустите** терминал и проверьте:

```bat
git --version
```

Затем:
1. Зарегистрируйтесь на https://github.com (бесплатно).
2. Создайте **новый публичный или приватный репозиторий** (кнопка «New»),
   название любое, например `roblox-deals-bot`. Остальное пустым.
3. Загрузите проект:

```bat
cd "C:\Users\ТB\Documents\Проект по умолчанию"
git init
git add .
git commit -m "Roblox deals bot"
git branch -M main
git remote add origin https://github.com/<ВАШ_ЛОГИН>/roblox-deals-bot.git
git push -u origin main
```

GitHub попросит логин/пароль — используйте **Personal Access Token**
(Settings → Developer settings → Personal access tokens → Fine-grained,
доступ к репозиторию) или встроенную авторизацию браузера.

Файлы `.env` (токен) и `deals.db` в git **не попадают** — это правильно.

---

## Вариант A. GitHub Actions (бесплатно, без карты) ⭐

Репозиторий на GitHub сам запускает проверку каждые 5 минут: парсит цены,
шлёт уведомления в Telegram и сохраняет базу обратно в репозиторий.
Сервер не нужен, карта не нужна.

**Что работает:** уведомления о выгодных предложениях, история цен,
список товаров из `config.py` (редактируется прямо на сайте GitHub с телефона).
**Что не работает:** команды и кнопки в Telegram (некому слать getUpdates) —
вместо `/check` используется кнопка *Run workflow* на GitHub, вместо
`/additem` — правка `config.py` на GitHub.

### Шаги

1. Пройдите **Шаг 0** выше (Git + GitHub) и загрузите проект.
   ⚠️ Сделайте репозиторий **публичным** — на публичных репозиториях
   GitHub Actions **безлимитны**; на приватных дают 2 000 минут/мес
   (при проверке каждые 5 минут ≈ 2 200 мин — не хватит, придётся
   поставить cron раз в час: `"17 * * * *"`).
2. Откройте репозиторий на GitHub → **Settings → Secrets and variables → Actions → New repository secret**:
   - Name: `BOT_TOKEN`
   - Secret: `8374841504:AAGOS0D2bxeRfjnErUjG_zvccaZLBudShmU`
3. Вкладка **Actions** → если workflows отключены, нажмите **«I understand my workflows, go ahead and enable them»**.
4. Слева выберите **Check deals** → справа **Run workflow** (ручной запуск для проверки).
5. Откройте лог запуска: должен завершиться зелёной галочкой с `=== Готово ===`,
   а в Telegram прийти сообщение с карточками предложений.
6. Дальше проверки пойдут сами каждые 5 минут.

### Как это устроено

- `.github/workflows/check.yml` — расписание (`*/5 * * * *`) и запуск `check_once.py`
- `check_once.py` — одна проверка: парсинг → сделки → отправка через Bot API → выход
- `deals.db` (сделки, история, списки) коммитится в репозиторий после каждого
  запуска — данные не теряются
- `run_day.txt` обновляется раз в день, чтобы GitHub не отключил расписание
  за «60 дней без активности» репозитория
- Кому слать: `NOTIFY_USER_IDS` в `config.py` (по умолчанию ваш ID)

### Управление списком товаров в этом режиме

Правьте `config.py` на сайте GitHub (кнопка ✏️ на файле →
«Edit this file» → «Commit changes»), например:

```python
"items": {
    "Dought Fruit": 45,        # целевая цена в ₽
    "Мой новый предмет": 500,
}
```

Через несколько секунд workflow подхватит изменения при следующей проверке.

### Если расписание отключилось

GitHub отключает `schedule` после 60 дней без активности репозитория
(обычно не происходит из-за `run_day.txt`, но проверяйте). Включается заново:
**Actions → Check deals → «Enable workflow»**.

---

## Вариант B. Railway (простой, платный trial)

Условия: был бесплатный trial-кредит, сейчас действует минимальный платный
тариф (~$5/мес) — актуальные условия смотрите на https://railway.com

1. Зарегистрируйтесь на railway.com (через GitHub — сразу доступ к репозиториям).
2. **New Project → Deploy from GitHub repo** → выберите `roblox-deals-bot`.
3. Railway сам подхватит `Procfile` (`worker: python bot.py`) и поставит зависимости
   из `requirements.txt`.
4. Вкладка **Variables** → добавьте:
   - `BOT_TOKEN` = `8374841504:AAGOS0D2bxeRfjnErUjG_zvccaZLBudShmU`
5. Если Railway создал сервис типа «Web Service» — измените тип на **Worker**
   (в настройках сервиса → Type), иначе будет искать HTTP-порт.
6. Деплой запустится сам; вкладка **Logs** покажет `Бот запущен!`.
7. Откройте бота в Telegram → `/start` должен ответить.

### Хранение базы (SQLite)

По умолчанию файловая система эфемерна: `deals.db` переживает перезапуски,
но **сбрасывается при новом деплое**. Чтобы не терять подписки и списки:

- Railway → сервис → **Volumes** → Add Volume, монтируется в `/data`,
  затем задайте переменную окружения `DB_PATH=/data/deals.db`
  (config.py уже поддерживает `DB_PATH` из окружения? — да: `os.getenv("DB_PATH", "deals.db")`).
- Или смиритесь: при деплое подписки сбрасываются (белый список и список
  товаров из `config.py` в коде — они сохраняются всегда).

---

## Вариант C. Render.com

1. Регистрация на https://render.com (через GitHub).
2. **New → Background Worker** (именно Worker, не Web Service — боту не нужен HTTP).
3. Connect GitHub repository → `roblox-deals-bot`.
4. Настройки:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
5. **Environment** → добавьте `BOT_TOKEN`.
6. Create Background Worker → вкладка **Logs**: ждём `Бот запущен!`.

> Бесплатный тариф Render не поддерживает Background Workers (они на платных
> тарифах), а бесплатный Web Service засыпает без HTTP-трафика — для бота
> нужен платный Worker или вариант C.

---

## Вариант D. Бесплатный VPS (Oracle Cloud Always Free)

Полностью бесплатно и без ограничений по времени, но регистрация сложнее
(нужна карта и проверка, бывают отказы).

1. https://www.oracle.com/cloud/free/ → создайте учётную запись.
2. Создайте виртуальную машину **Ubuntu** (VM.Standard.E2.1.Micro, Always Free).
3. Подключитесь по SSH (PuTTY/Windows Terminal: `ssh ubuntu@<ip>`).
4. Установите зависимости:

```bash
sudo apt update && sudo apt install -y python3-pip
git clone https://github.com/<ВАШ_ЛОГИН>/roblox-deals-bot.git
cd roblox-deals-bot
pip3 install -r requirements.txt
echo 'BOT_TOKEN=8374841504:AAGOS0D2bxeRfjnErUjG_zvccaZLBudShmU' > .env
```

5. Запустите как службу, чтобы бот переживал перезагрузку:

```bash
sudo tee /etc/systemd/system/robloxbot.service > /dev/null <<'EOF'
[Unit]
Description=Roblox Deals Telegram Bot
After=network.target

[Service]
WorkingDirectory=/home/ubuntu/roblox-deals-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now robloxbot
sudo systemctl status robloxbot    # должен быть active (running)
journalctl -u robloxbot -f         # логи в реальном времени
```

6. `deals.db` лежит в папке проекта и сохраняется навсегда.

---

## Другие варианты

| Сервис | Цена | Примечание |
|---|---|---|
| Fly.io | trial-кредит | CLI `fly launch`, нужна карта |
| VPS (Hetzner/DigitalOcean/Vultr) | от ~$4/мес | Полный контроль, `systemd` как в варианте D |
| Домашний ПК + Tailscale | бесплатно | Работает, пока ПК включён |

---

## Переменные окружения

| Переменная | Где | Значение |
|---|---|---|
| `BOT_TOKEN` | **обязательно**, `.env` или панель хостинга | токен от @BotFather |
| `PROXY_URL` | необязательно | HTTP(S)/SOCKS прокси для Telegram |
| `DB_PATH` | необязательно | путь к SQLite, по умолчанию `deals.db` |

---

## Где выставить свой список товаров

### 1. В боте (рекомендуется, работает и в облаке)

```
/additem mm2 Harvester 500
/additem blox Dought Fruit 45
/additem yba Lucky Arrow 6
```

Просмотр: `/myitems` или кнопка «📋 Мои товары».
Удаление: пока удаление только из кода/БД; товар можно не подтверждать
при автопредложении (❌).

### 2. В коде (`config.py` → `GAMES`)

```python
"items": {
    "Название предмета": 1000,  # целевая цена в ₽
}
```

После правки — закоммитьте и запушьте, облако пересоберётся само.

**Название должно быть на английском** (как на ggsel.net) и содержать
указание игры: например, одиночное `Yeti` принимается только если в лоте
есть маркер игры (`Blox Fruits`, `BF`, `фрукт`). Фразы вроде
`Fiend Yeti`, `Flowerwood Set` работают вместе с маркером.

### Максимум списка

- **Оптимально**: 50–200 предметов на пользователя (бесшумно, быстро).
- **Максимум**: ~1000 предметов — каждая проверка делает один запрос
  на предмет с паузой 0.8 с, 1000 предметов ≈ 15 минут на цикл
  (при интервале 5 минут ставьте `CHECK_INTERVAL_MINUTES` больше).
- SQLite выдерживает десятки тысяч записей — реальное ограничение —
  время парсинга и лимиты маркетплейса.
- Для списка **всех** пользователей суммируйте их товары.

---

## Обновление бота

```bat
git add .
git commit -m "изменения"
git push
```

Railway/Render перезапустятся автоматически. На VPS:

```bash
sudo systemctl restart robloxbot
```

## Мониторинг

- Логи в панели Railway/Render (вкладка Logs) или `journalctl -u robloxbot -f`.
- В логах каждые 5 минут: `Запуск фоновой проверки цен (ggsel)...`
  и `Новых выгодных предложений: N`.
- Тест парсинга без Telegram: `py -3 test_bot.py` (Windows) / `python3 test_bot.py`.
