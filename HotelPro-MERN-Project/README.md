# HotelPro — MERN Hotel Booking Starter

A starter hotel booking app using React, Express, Node.js and MongoDB.

## Features
- Register/login with JWT authentication and bcrypt password hashing
- Browse seeded hotel rooms
- Create bookings with date validation and overlap checks
- View and cancel your bookings
- Responsive hotel landing page

## Run locally
Requirements: Node.js 18+, npm, MongoDB.

Backend:
1. `cd server`
2. `npm install`
3. Copy `.env.example` to `.env`, then set `JWT_SECRET` and `MONGODB_URI`
4. `npm run dev`

Frontend (second terminal):
1. `cd client`
2. `npm install`
3. Copy `.env.example` to `.env`
4. `npm run dev`

Frontend runs at `http://localhost:5173`; API at `http://localhost:5000`.

Never commit real `.env` files or credentials. This is a learning/demo starter, not production-ready. Add payment integration, email verification, rate limiting, tests, admin tools, and a security review before real-world use.
