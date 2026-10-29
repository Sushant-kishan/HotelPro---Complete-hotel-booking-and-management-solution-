import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import mongoose from "mongoose";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
dotenv.config();

const app = express();
app.use(cors({ origin: process.env.CLIENT_ORIGIN || "http://localhost:5173" }));
app.use(express.json());

const User = mongoose.model("User", new mongoose.Schema({
  name: { type: String, required: true, trim: true },
  email: { type: String, required: true, unique: true, lowercase: true, trim: true },
  passwordHash: { type: String, required: true }, role: { type: String, default: "guest" }
}, { timestamps: true }));
const Room = mongoose.model("Room", new mongoose.Schema({
  name: { type: String, required: true }, type: { type: String, required: true },
  description: String, pricePerNight: { type: Number, min: 1, required: true },
  capacity: { type: Number, min: 1, required: true }, amenities: [String]
}, { timestamps: true }));
const Booking = mongoose.model("Booking", new mongoose.Schema({
  user: { type: mongoose.Schema.Types.ObjectId, ref: "User", required: true },
  room: { type: mongoose.Schema.Types.ObjectId, ref: "Room", required: true },
  checkIn: { type: Date, required: true }, checkOut: { type: Date, required: true },
  guests: { type: Number, min: 1, required: true }, totalPrice: { type: Number, required: true },
  status: { type: String, enum: ["confirmed", "cancelled"], default: "confirmed" }
}, { timestamps: true }));

function requireAuth(req, res, next) {
  try {
    const token = (req.headers.authorization || "").replace(/^Bearer\\s+/i, "");
    if (!token) return res.status(401).json({ message: "Please sign in." });
    req.user = jwt.verify(token, process.env.JWT_SECRET); next();
  } catch { return res.status(401).json({ message: "Invalid or expired session." }); }
}
app.get("/api/health", (_req,res) => res.json({ status:"ok", name:"HotelPro API" }));
app.post("/api/auth/register", async (req,res) => {
  try {
    const { name, email, password } = req.body;
    if (!name?.trim() || !email?.trim() || !password || password.length < 8)
      return res.status(400).json({ message:"Name, email and password (8+ characters) are required." });
    if (await User.findOne({ email: email.toLowerCase().trim() }))
      return res.status(409).json({ message:"Email is already registered." });
    const user = await User.create({ name, email, passwordHash: await bcrypt.hash(password, 12) });
    const token = jwt.sign({ id:user.id, role:user.role }, process.env.JWT_SECRET, { expiresIn:"7d" });
    res.status(201).json({ token, user:{ id:user.id, name:user.name, email:user.email } });
  } catch { res.status(500).json({ message:"Registration failed." }); }
});
app.post("/api/auth/login", async (req,res) => {
  try {
    const user = await User.findOne({ email:req.body.email?.toLowerCase().trim() });
    if (!user || !(await bcrypt.compare(req.body.password || "", user.passwordHash)))
      return res.status(401).json({ message:"Invalid email or password." });
    const token = jwt.sign({ id:user.id, role:user.role }, process.env.JWT_SECRET, { expiresIn:"7d" });
    res.json({ token, user:{ id:user.id, name:user.name, email:user.email } });
  } catch { res.status(500).json({ message:"Login failed." }); }
});
app.get("/api/rooms", async (_req,res) => {
  try { res.json(await Room.find().sort({ pricePerNight:1 })); }
  catch { res.status(500).json({ message:"Could not load rooms." }); }
});
app.get("/api/bookings", requireAuth, async (req,res) => {
  try { res.json(await Booking.find({ user:req.user.id }).populate("room").sort({ createdAt:-1 })); }
  catch { res.status(500).json({ message:"Could not load bookings." }); }
});
app.post("/api/bookings", requireAuth, async (req,res) => {
  try {
    const { roomId, checkIn, checkOut, guests } = req.body;
    const start = new Date(checkIn), end = new Date(checkOut), count = Number(guests);
    if (!roomId || isNaN(start) || isNaN(end) || end <= start || !Number.isInteger(count) || count < 1)
      return res.status(400).json({ message:"Enter valid dates and guest count." });
    const room = await Room.findById(roomId);
    if (!room) return res.status(404).json({ message:"Room not found." });
    if (count > room.capacity) return res.status(400).json({ message:`Room capacity is ${room.capacity}.` });
    const conflict = await Booking.findOne({ room:roomId, status:"confirmed", checkIn:{ $lt:end }, checkOut:{ $gt:start } });
    if (conflict) return res.status(409).json({ message:"Room is already booked for these dates." });
    const nights = Math.ceil((end-start)/86400000);
    const booking = await Booking.create({ user:req.user.id, room:roomId, checkIn:start, checkOut:end, guests:count, totalPrice:nights*room.pricePerNight });
    res.status(201).json(await booking.populate("room"));
  } catch { res.status(400).json({ message:"Could not create booking." }); }
});
app.delete("/api/bookings/:id", requireAuth, async (req,res) => {
  try {
    const booking = await Booking.findOne({ _id:req.params.id, user:req.user.id });
    if (!booking) return res.status(404).json({ message:"Booking not found." });
    booking.status = "cancelled"; await booking.save();
    res.json({ message:"Booking cancelled." });
  } catch { res.status(400).json({ message:"Invalid booking ID." }); }
});
async function seedRooms() {
  if (await Room.countDocuments()) return;
  await Room.insertMany([
    { name:"Garden Deluxe", type:"Deluxe", description:"A peaceful room with garden views.", pricePerNight:3200, capacity:2, amenities:["Wi-Fi","Breakfast","Air conditioning"] },
    { name:"Executive Suite", type:"Suite", description:"A refined suite for work or a special stay.", pricePerNight:5800, capacity:3, amenities:["Wi-Fi","Breakfast","Workspace"] },
    { name:"Family Comfort", type:"Family", description:"Comfortable space for a family getaway.", pricePerNight:4500, capacity:4, amenities:["Wi-Fi","Family space","Air conditioning"] }
  ]);
}
if (!process.env.JWT_SECRET) { console.error("Set JWT_SECRET in server/.env"); process.exit(1); }
mongoose.connect(process.env.MONGODB_URI || "mongodb://127.0.0.1:27017/hotelpro")
  .then(async () => { await seedRooms(); app.listen(process.env.PORT || 5000, () => console.log("HotelPro API started")); })
  .catch(err => { console.error("MongoDB connection failed:", err.message); process.exit(1); });
