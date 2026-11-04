# Security policy

Please **do not open a public issue** for security problems. Email **mmowaisq@gmail.com** with steps to
reproduce. You'll get a reply within a few days, and a fix or mitigation will be released as soon as possible.

Deployment advice: set `API_KEY` on any server reachable from the internet, keep the SQLite file and `.env`
outside the web root, and back up the database before upgrades.
