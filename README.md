
Dailybread is a website and Discord integration that sends embeds or containers into Discord channels, with Bible verse search across NLT/NIV/NKJV and simple webpage navigation.

## Database configuration

DailyBread connects to PostgreSQL from the backend only. Configure either `DATABASE_URL` or all of `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, and `DATABASE_PASSWORD`. Use the existing PostgreSQL Docker service name as `DATABASE_HOST` on the shared Docker network; no public PostgreSQL port mapping is required.
