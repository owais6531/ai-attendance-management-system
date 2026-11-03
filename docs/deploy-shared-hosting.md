# Deploy on cPanel shared hosting

Works on hosts that offer **"Setup Python App"** (Phusion Passenger) in cPanel, Python 3.11+.

1. **Create a MySQL database + user** in cPanel → *MySQL Databases*. Give the user all privileges on it.
2. **Upload the code** (Git Version Control in cPanel, or zip upload) to e.g. `~/attendance`, **outside**
   `public_html`.
3. cPanel → **Setup Python App** → *Create Application*:
   - Python version: 3.11 or newer
   - Application root: `attendance`
   - Application URL: the domain/subdomain you want
   - Application startup file: `passenger_wsgi.py`
   - Application entry point: `application`
4. In the same screen, add **environment variables**:
   - `DATABASE_URL` = `mysql+pymysql://DBUSER:DBPASS@localhost:3306/DBNAME`
     (URL-encode special characters in the password, e.g. `@` → `%40`)
   - `API_KEY` = a long random value (recommended on a public server)
5. Copy the "Enter to the virtual environment" command shown by cPanel, open **Terminal**, run it, then:
   ```bash
   pip install -r requirements.txt
   python scripts/create_tables.py
   ```
6. Click **Restart** in Setup Python App and open your URL.

**Notes**
- Without MySQL you can use SQLite: `DATABASE_URL=sqlite:////home/USER/attendance/data/attendance.db`
  (keep the file outside `public_html`).
- If `pip install pandas` fails because of memory limits, ask the host to raise them or use a VPS/Docker.
- Take a database backup (cPanel → Backup, or phpMyAdmin export) before every update.
