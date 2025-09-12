# AgroFruit 2007 – Муштерии (Web)

Flask веб-апликација со најава, SQLite база и извоз во TXT.

## Локално стартување
1) Инсталирај Python 3.10+
2) Во папката на проектот:
```
python -m venv venv
venv\Scripts\activate    # на Windows
# или: source venv/bin/activate  (на macOS/Linux)
pip install -r requirements.txt
```
3) (Опц.) Копирај `.env.example` во `.env` и промени `FLASK_SECRET` и `ADMIN_EMAIL`.
4) Иницијализирај база + админ корисник:
```
flask --app app.py init-db
```
5) Стартувај:
```
flask --app app.py run
```
Отвори http://127.0.0.1:5000

## Најава
- Ако користиш `init-db`, ќе се креира админ со email од `ADMIN_EMAIL` и лозинка `admin123` (смени ја веднаш по најава!).
- Ако нема корисници, може да се регистрира прв админ на /register

## Деплој (брзо)
- **Render.com / Railway.app / Fly.io**: додади нов веб-сервис
  - Python build, `pip install -r requirements.txt`
  - Start command: `gunicorn -w 2 -b 0.0.0.0:$PORT app:app` (додај `gunicorn` во requirements ако го користиш)
  - Set `FLASK_SECRET` и (опц.) `ADMIN_EMAIL` како environment variables
  - Ранни `flask --app app.py init-db` еднаш преку shell за да се креира админ

## Интеграција со агроfruit2007 веб-страна
- Хостирај ја оваа апликација како поддомен, пример `app.agrofruit2007.com`
- На главниот сајт (статичен), стави линк кон оваа апликација.
- Подоцна можеме да префрлиме база на **PostgreSQL** (на Render/Railway) и да користиме **Supabase Auth** ако сакаш повеќе корисници.

## Експорт
- TXT по година: `/export/<cid>/<year>.txt`
- TXT збирно за сите години: `/export/<cid>/all.txt`
- TXT batch zip: `/export/<cid>/batch.zip`

