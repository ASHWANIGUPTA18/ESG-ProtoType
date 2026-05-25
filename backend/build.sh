#!/usr/bin/env bash
set -o errexit

# Build frontend
cd ../frontend
npm install
npm run build
cd ../backend

# Backend setup
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py bootstrap_demo
