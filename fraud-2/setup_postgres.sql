CREATE USER fraud_user WITH PASSWORD 'fraud123';
CREATE DATABASE fraud_db OWNER fraud_user;
GRANT ALL PRIVILEGES ON DATABASE fraud_db TO fraud_user;
