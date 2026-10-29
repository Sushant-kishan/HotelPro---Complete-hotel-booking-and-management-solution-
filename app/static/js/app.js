/**
 * HotelPro Enterprise Hospitality Management Client Application
 * Communicates with FastAPI backend under /api/v1/
 */

const API_BASE = "/api/v1";

const state = {
  propertyId: "prop-horizon-miami",
  token: null,
  currentUser: null,
  activeMainTab: "guest-booking", // 'guest-booking', 'guest-folio', 'staff-portal'
  activeStaffTab: "frontdesk",    // 'frontdesk', 'housekeeping', 'folios', 'nightaudit', 'audit'
  businessDate: new Date().toISOString().split("T")[0],
  // Preconfigured demo credentials
  staffPresets: [
    { label: "Front Desk (Marcus Chen)", username: "frontdesk", password: "frontdeskpassword123", role: "FrontDesk" },
    { label: "General Manager (Elena Rostova)", username: "manager", password: "managerpassword123", role: "PropertyManager" },
    { label: "Housekeeping (Rosa Morales)", username: "housekeeper", password: "cleanpassword123", role: "Housekeeping" },
    { label: "Night Auditor (David Sterling)", username: "auditor", password: "auditpassword123", role: "Auditor" },
    { label: "Super Admin (Alex Vance)", username: "admin", password: "adminpassword123", role: "SuperAdmin" },
  ]
};

// --- Toast Notifications ---
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  const bgColors = {
    info: "bg-slate-800 text-white",
    success: "bg-emerald-600 text-white",
    warning: "bg-amber-600 text-white",
    error: "bg-rose-600 text-white"
  };
  toast.className = `p-4 rounded-lg shadow-lg flex items-center justify-between space-x-3 text-sm transition transform duration-300 ${bgColors[type] || bgColors.info}`;
  toast.innerHTML = `<span>${message}</span><button onclick="this.parentElement.remove()" class="text-white hover:opacity-75">✕</button>`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4500);
}

// --- Fetch Wrapper with Auth ---
async function apiRequest(endpoint, method = "GET", body = null) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }
  const config = { method, headers };
  if (body) {
    config.body = JSON.stringify(body);
  }
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, config);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = data.detail || "Request failed";
      showToast(err, "error");
      throw new Error(err);
    }
    return data;
  } catch (err) {
    console.error("API error:", err);
    throw err;
  }
}

// --- Navigation Tabs ---
function switchMainTab(tab) {
  state.activeMainTab = tab;
  document.querySelectorAll(".main-tab-btn").forEach(btn => {
    btn.classList.toggle("text-sky-600", btn.dataset.tab === tab);
    btn.classList.toggle("border-sky-600", btn.dataset.tab === tab);
    btn.classList.toggle("border-b-2", btn.dataset.tab === tab);
  });
  document.getElementById("view-guest-booking").classList.toggle("hidden", tab !== "guest-booking");
  document.getElementById("view-guest-folio").classList.toggle("hidden", tab !== "guest-folio");
  document.getElementById("view-staff-portal").classList.toggle("hidden", tab !== "staff-portal");

  if (tab === "guest-booking") {
    searchRooms();
  } else if (tab === "staff-portal") {
    if (!state.currentUser) {
      // Auto-login default front desk staff for convenience
      loginStaffPreset("frontdesk", "frontdeskpassword123");
    } else {
      switchStaffTab(state.activeStaffTab);
    }
  }
}

function switchStaffTab(tab) {
  state.activeStaffTab = tab;
  document.querySelectorAll(".staff-tab-btn").forEach(btn => {
    btn.classList.toggle("bg-sky-50", btn.dataset.tab === tab);
    btn.classList.toggle("text-sky-700", btn.dataset.tab === tab);
    btn.classList.toggle("font-semibold", btn.dataset.tab === tab);
  });
  document.querySelectorAll(".staff-panel").forEach(panel => {
    panel.classList.toggle("hidden", panel.id !== `panel-${tab}`);
  });

  if (tab === "frontdesk") loadFrontDeskData();
  if (tab === "housekeeping") loadHousekeepingBoard();
  if (tab === "folios") loadFoliosView();
  if (tab === "nightaudit") loadNightAuditChecklist();
  if (tab === "audit") loadAuditLedger();
}

// --- Authentication & MFA ---
async function loginStaffPreset(username, password) {
  try {
    const res = await apiRequest("/auth/login", "POST", { username, password });
    if (res.mfa_required) {
      // Prompt TOTP MFA modal
      openMfaModal(username);
    } else {
      state.token = res.access_token;
      state.currentUser = res.user;
      renderStaffHeader();
      switchStaffTab(state.activeStaffTab);
      showToast(`Signed in as ${res.user.full_name} (${res.user.role})`, "success");
    }
  } catch (e) {}
}

function openMfaModal(username) {
  const modal = document.getElementById("mfa-modal");
  document.getElementById("mfa-modal-username").innerText = username;
  document.getElementById("mfa-code-input").value = "";
  modal.classList.remove("hidden");
}

function closeMfaModal() {
  document.getElementById("mfa-modal").classList.add("hidden");
}

async function submitMfaCode() {
  const username = document.getElementById("mfa-modal-username").innerText;
  const code = document.getElementById("mfa-code-input").value.trim();
  if (!code) {
    showToast("Please enter 6-digit code or backup token", "warning");
    return;
  }
  try {
    const res = await apiRequest("/auth/mfa/verify", "POST", { username, totp_code: code });
    state.token = res.access_token;
    state.currentUser = res.user;
    closeMfaModal();
    renderStaffHeader();
    switchStaffTab(state.activeStaffTab);
    showToast(`MFA Verified! Welcome, ${res.user.full_name}`, "success");
  } catch (e) {}
}

async function quickFillMfa() {
  // Uses backup code seeded in app/seed.py
  document.getElementById("mfa-code-input").value = "A1B2-C3D4";
}

function renderStaffHeader() {
  const user = state.currentUser;
  if (!user) return;
  document.getElementById("staff-profile-pill").innerHTML = `
    <div class="flex items-center space-x-2 bg-slate-100 py-1.5 px-3 rounded-full text-xs font-medium text-slate-700">
      <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
      <span>${user.full_name}</span>
      <span class="bg-sky-100 text-sky-800 text-[10px] px-2 py-0.5 rounded uppercase font-bold">${user.role}</span>
      ${user.mfa_authenticated ? '<span class="text-emerald-600 font-bold" title="MFA Verified">🔒 MFA</span>' : ''}
    </div>
  `;
}

// --- Guest Booking Engine ---
async function searchRooms() {
  const checkIn = document.getElementById("search-checkin").value;
  const checkOut = document.getElementById("search-checkout").value;
  const promo = document.getElementById("search-promo").value.trim();

  try {
    const data = await apiRequest(`/inventory/availability?property_id=${state.propertyId}&check_in_date=${checkIn}&check_out_date=${checkOut}`);
    renderRoomListings(data.categories, checkIn, checkOut, promo);
  } catch (e) {}
}

function renderRoomListings(categories, checkIn, checkOut, promo) {
  const list = document.getElementById("room-listings");
  list.innerHTML = "";

  categories.forEach(cat => {
    let rate = cat.dynamic_nightly_rate;
    let promoBadge = "";
    if (promo.toUpperCase() === "CORP20") {
      rate = Math.round(rate * 0.8 * 100) / 100;
      promoBadge = `<span class="bg-purple-100 text-purple-700 text-xs px-2 py-0.5 rounded font-bold">20% Corporate Rate Applied</span>`;
    }

    const card = document.createElement("div");
    card.className = "bg-white border rounded-xl shadow-sm p-6 hover:shadow-md transition flex flex-col justify-between";
    card.innerHTML = `
      <div>
        <div class="flex justify-between items-start mb-2">
          <h3 class="text-lg font-bold text-slate-900">${cat.name}</h3>
          <span class="text-xs px-2.5 py-1 rounded-full font-semibold ${cat.available ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}">
            ${cat.available ? `${cat.rooms_remaining} Available` : 'Sold Out'}
          </span>
        </div>
        <p class="text-xs text-slate-500 mb-4">${cat.description || ''}</p>
        <div class="flex items-center space-x-2 text-xs text-slate-600 mb-4">
          <span>👥 Up to ${cat.max_occupancy} guests</span>
          <span>•</span>
          <span>🌊 Ocean View</span>
          <span>•</span>
          <span>📶 Free WiFi</span>
        </div>
      </div>
      <div class="border-t pt-4 flex items-center justify-between">
        <div>
          <div class="text-2xl font-extrabold text-slate-900">$${rate} <span class="text-xs font-normal text-slate-500">/ night</span></div>
          ${cat.dynamic_nightly_rate > cat.base_rate ? `<span class="text-[11px] text-amber-600 font-medium">⚡ High Demand Rate</span>` : ''}
          ${promoBadge}
        </div>
        <button 
          onclick="openBookingModal('${cat.id}', '${cat.name}', ${rate}, '${checkIn}', '${checkOut}')"
          ${cat.available ? '' : 'disabled'}
          class="px-4 py-2 text-sm font-semibold rounded-lg ${cat.available ? 'bg-sky-600 hover:bg-sky-700 text-white' : 'bg-slate-200 text-slate-400 cursor-not-allowed'}">
          Book Now
        </button>
      </div>
    `;
    list.appendChild(card);
  });
}

function openBookingModal(roomTypeId, roomTypeName, rate, checkIn, checkOut) {
  document.getElementById("book-modal-roomtype-id").value = roomTypeId;
  document.getElementById("book-modal-roomtype-name").innerText = roomTypeName;
  document.getElementById("book-modal-rate").innerText = `$${rate}/night`;
  document.getElementById("book-modal-checkin").value = checkIn;
  document.getElementById("book-modal-checkout").value = checkOut;
  document.getElementById("booking-modal").classList.remove("hidden");
}

function closeBookingModal() {
  document.getElementById("booking-modal").classList.add("hidden");
}

async function submitBooking() {
  const roomTypeId = document.getElementById("book-modal-roomtype-id").value;
  const checkIn = document.getElementById("book-modal-checkin").value;
  const checkOut = document.getElementById("book-modal-checkout").value;
  const firstName = document.getElementById("book-modal-first").value.trim();
  const lastName = document.getElementById("book-modal-last").value.trim();
  const email = document.getElementById("book-modal-email").value.trim();
  const phone = document.getElementById("book-modal-phone").value.trim();
  const promo = document.getElementById("search-promo").value.trim();

  if (!firstName || !lastName || !email || !phone) {
    showToast("Please fill in all guest contact details", "warning");
    return;
  }

  try {
    const payload = {
      property_id: state.propertyId,
      room_type_id: roomTypeId,
      check_in_date: checkIn,
      check_out_date: checkOut,
      first_name: firstName,
      last_name: lastName,
      email: email,
      phone: phone,
      discount_code: promo || null,
      card_token: "tok_pci_visa_instant_booking_token",
      channel: "DIRECT_WEB"
    };

    const res = await apiRequest("/reservations/book", "POST", payload);
    closeBookingModal();
    showToast(`Reservation Confirmed! Code: ${res.booking_reference}`, "success");
    
    // Switch to guest folio tab to show receipt
    document.getElementById("lookup-ref-input").value = res.booking_reference;
    switchMainTab("guest-folio");
    lookupGuestFolio();
  } catch (e) {}
}

// --- Guest Folio & Digital Key Lookup ---
async function lookupGuestFolio() {
  const ref = document.getElementById("lookup-ref-input").value.trim();
  if (!ref) {
    showToast("Enter a booking reference code (e.g. HP-2026-...)", "warning");
    return;
  }
  try {
    const res = await apiRequest(`/reservations/lookup/${ref}`);
    renderGuestFolioDetails(res);
  } catch (e) {}
}

function renderGuestFolioDetails(data) {
  const card = document.getElementById("guest-folio-result");
  card.classList.remove("hidden");

  document.getElementById("folio-ref").innerText = data.booking_reference;
  document.getElementById("folio-guest").innerText = `${data.guest_first_name} ${data.guest_last_name}`;
  document.getElementById("folio-status").innerText = data.status;
  document.getElementById("folio-dates").innerText = `${data.check_in_date} to ${data.check_out_date}`;
  document.getElementById("folio-room").innerText = data.room_number ? `Room ${data.room_number}` : "Not assigned yet";
  
  // Total balance across folios
  let totalBal = 0;
  let itemsHtml = "";
  (data.folios || []).forEach(f => {
    totalBal += f.balance;
    (f.items || []).forEach(item => {
      itemsHtml += `
        <tr class="border-b text-xs">
          <td class="py-2 font-medium">${item.description}</td>
          <td class="py-2 text-slate-500">${item.category}</td>
          <td class="py-2 text-right">$${item.amount.toFixed(2)}</td>
          <td class="py-2 text-right text-slate-500">$${item.tax_amount.toFixed(2)}</td>
        </tr>
      `;
    });
  });

  document.getElementById("folio-total-balance").innerText = `$${totalBal.toFixed(2)}`;
  document.getElementById("folio-items-table").innerHTML = itemsHtml || `<tr><td colspan="4" class="py-4 text-center text-xs text-slate-400">No charges posted yet.</td></tr>`;

  // Digital keycard widget
  const keyWidget = document.getElementById("digital-key-widget");
  if (data.status === "CHECKED_IN" && data.room_number) {
    keyWidget.classList.remove("hidden");
    document.getElementById("digital-key-room").innerText = `Room ${data.room_number}`;
  } else {
    keyWidget.classList.add("hidden");
  }
}

// --- Front Desk Operations (< 60s Check-In / Check-Out) ---
async function loadFrontDeskData() {
  try {
    const arrivals = await apiRequest(`/frontdesk/arrivals?property_id=${state.propertyId}`);
    const departures = await apiRequest(`/frontdesk/departures?property_id=${state.propertyId}`);
    renderArrivalsList(arrivals);
    renderDeparturesList(departures);
  } catch (e) {}
}

function renderArrivalsList(arrivals) {
  const tbody = document.getElementById("frontdesk-arrivals-table");
  tbody.innerHTML = "";
  if (arrivals.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-xs text-slate-400">No pending arrivals for today.</td></tr>`;
    return;
  }
  arrivals.forEach(a => {
    const tr = document.createElement("tr");
    tr.className = "border-b text-xs hover:bg-slate-50";
    tr.innerHTML = `
      <td class="py-3 font-bold text-sky-700">${a.booking_reference}</td>
      <td class="py-3 font-medium">${a.guest_name} <span class="text-[10px] text-slate-400">(${a.channel})</span></td>
      <td class="py-3">${a.room_type_name}</td>
      <td class="py-3">${a.check_in_date} → ${a.check_out_date}</td>
      <td class="py-3">${a.special_requests || '—'}</td>
      <td class="py-3 text-right">
        <button onclick="openCheckInModal('${a.id}', '${a.guest_name}', '${a.room_type_id}', '${a.room_type_name}')"
          class="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-3 py-1.5 rounded shadow-sm text-xs">
          ⚡ 60s Check-In
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderDeparturesList(departures) {
  const tbody = document.getElementById("frontdesk-departures-table");
  tbody.innerHTML = "";
  if (departures.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-xs text-slate-400">No departing rooms for today.</td></tr>`;
    return;
  }
  departures.forEach(d => {
    const tr = document.createElement("tr");
    tr.className = "border-b text-xs hover:bg-slate-50";
    tr.innerHTML = `
      <td class="py-3 font-bold text-slate-900">Room ${d.room_number || 'N/A'}</td>
      <td class="py-3 font-medium">${d.guest_name}</td>
      <td class="py-3 text-slate-500">${d.booking_reference}</td>
      <td class="py-3 font-bold ${d.total_open_balance > 0 ? 'text-rose-600' : 'text-emerald-600'}">$${d.total_open_balance.toFixed(2)}</td>
      <td class="py-3 text-right">
        <button onclick="executeCheckOut('${d.id}', '${d.guest_name}', '${d.room_number}')"
          class="bg-rose-600 hover:bg-rose-700 text-white font-semibold px-3 py-1.5 rounded shadow-sm text-xs">
          ⚡ Settle & Check-Out
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function openCheckInModal(resId, guestName, roomTypeId, roomTypeName) {
  document.getElementById("checkin-modal-res-id").value = resId;
  document.getElementById("checkin-modal-guest-name").innerText = guestName;
  document.getElementById("checkin-modal-room-type").innerText = roomTypeName;

  // Load assignable clean rooms
  const rooms = await apiRequest(`/frontdesk/assignable-rooms?property_id=${state.propertyId}&room_type_id=${roomTypeId}`);
  const select = document.getElementById("checkin-modal-room-select");
  select.innerHTML = "";
  if (rooms.length === 0) {
    select.innerHTML = `<option value="">No clean rooms ready! (Call Housekeeping)</option>`;
  } else {
    rooms.forEach(r => {
      select.innerHTML += `<option value="${r.id}">Room ${r.room_number} (Floor ${r.floor} • ${r.housekeeping_status})</option>`;
    });
  }
  document.getElementById("checkin-modal").classList.remove("hidden");
}

function closeCheckInModal() {
  document.getElementById("checkin-modal").classList.add("hidden");
}

async function executeCheckIn() {
  const resId = document.getElementById("checkin-modal-res-id").value;
  const roomId = document.getElementById("checkin-modal-room-select").value;
  const holdAmt = parseFloat(document.getElementById("checkin-modal-hold-amt").value) || 100.0;

  if (!roomId) {
    showToast("Please select a clean room to assign", "warning");
    return;
  }

  try {
    const res = await apiRequest("/frontdesk/check-in", "POST", {
      reservation_id: resId,
      room_id: roomId,
      card_token: "tok_pci_visa_frontdesk_token",
      incidental_deposit_amount: holdAmt
    });

    closeCheckInModal();
    showToast(`Sub-60s Check-In Complete! Room ${res.room_number} Issued. Keycard Active.`, "success");
    
    // Show keycard encoder alert
    alert(`🔑 KEYCARD ENCODER SIMULATOR\n-------------------------\nSystem: ENC-HQ-FL1-DESK1\nRoom: ${res.room_number}\nAuth Token: ${res.keycard.key_token}\nRFID Track: ${res.keycard.rfid_track_data}\nBLE Payload: ${res.keycard.ble_payload}\nValid Until: ${res.keycard.valid_until}`);

    loadFrontDeskData();
  } catch (e) {}
}

async function executeCheckOut(resId, guestName, roomNumber) {
  if (!confirm(`Finalize expedited checkout for ${guestName} (Room ${roomNumber})? Folio balances will be automatically captured.`)) {
    return;
  }
  try {
    const res = await apiRequest("/frontdesk/check-out", "POST", { reservation_id: resId });
    showToast(`Checked out! Room ${roomNumber} updated to DIRTY. Housekeeping task queued.`, "success");
    loadFrontDeskData();
  } catch (e) {}
}

// --- Housekeeping Board ---
async function loadHousekeepingBoard() {
  try {
    const rooms = await apiRequest(`/housekeeping/board?property_id=${state.propertyId}`);
    const grid = document.getElementById("housekeeping-grid");
    grid.innerHTML = "";

    rooms.forEach(r => {
      const badgeClasses = {
        CLEAN: "badge-clean",
        INSPECTED: "badge-inspected",
        DIRTY: "badge-dirty",
        IN_PROGRESS: "badge-progress",
        OUT_OF_ORDER: "badge-ooo"
      };

      const card = document.createElement("div");
      card.className = "bg-white border rounded-xl p-4 shadow-sm flex flex-col justify-between";
      card.innerHTML = `
        <div>
          <div class="flex justify-between items-center mb-2">
            <span class="text-xl font-extrabold text-slate-900">Room ${r.room_number}</span>
            <span class="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${badgeClasses[r.housekeeping_status] || 'badge-clean'}">
              ${r.housekeeping_status}
            </span>
          </div>
          <div class="text-xs text-slate-500 mb-2">Floor ${r.floor} • ${r.room_type_name}</div>
          <div class="text-[11px] font-medium ${r.operational_status === 'OCCUPIED' ? 'text-purple-700' : 'text-slate-600'}">
            Status: ${r.operational_status}
          </div>
          ${r.active_task_id ? `<div class="mt-2 text-[10px] bg-amber-50 text-amber-800 p-1.5 rounded border border-amber-200">🧹 ${r.task_type}</div>` : ''}
        </div>
        <div class="mt-4 border-t pt-3 flex flex-wrap gap-1">
          <button onclick="setRoomCleanliness('${r.id}', 'DIRTY')" class="text-[10px] px-2 py-1 bg-rose-50 text-rose-700 border border-rose-200 rounded font-semibold hover:bg-rose-100">Dirty</button>
          <button onclick="setRoomCleanliness('${r.id}', 'IN_PROGRESS')" class="text-[10px] px-2 py-1 bg-amber-50 text-amber-700 border border-amber-200 rounded font-semibold hover:bg-amber-100">In Progress</button>
          <button onclick="setRoomCleanliness('${r.id}', 'CLEAN')" class="text-[10px] px-2 py-1 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded font-semibold hover:bg-emerald-100">Clean</button>
          <button onclick="setRoomCleanliness('${r.id}', 'INSPECTED')" class="text-[10px] px-2 py-1 bg-sky-50 text-sky-700 border border-sky-200 rounded font-semibold hover:bg-sky-100">Inspect</button>
        </div>
      `;
      grid.appendChild(card);
    });
  } catch (e) {}
}

async function setRoomCleanliness(roomId, newStatus) {
  try {
    await apiRequest("/housekeeping/update-status", "POST", { room_id: roomId, status: newStatus });
    showToast(`Room updated to ${newStatus}`, "success");
    loadHousekeepingBoard();
  } catch (e) {}
}

// --- Folios & Split Billing ---
async function loadFoliosView() {
  try {
    const departures = await apiRequest(`/frontdesk/departures?property_id=${state.propertyId}`);
    const select = document.getElementById("folio-reservation-select");
    select.innerHTML = "";
    if (departures.length === 0) {
      select.innerHTML = `<option value="">No in-house reservations found</option>`;
      return;
    }
    departures.forEach(d => {
      select.innerHTML += `<option value="${d.id}">${d.guest_name} (Room ${d.room_number})</option>`;
    });
    refreshActiveFolio();
  } catch (e) {}
}

async function refreshActiveFolio() {
  const resId = document.getElementById("folio-reservation-select").value;
  if (!resId) return;

  try {
    const folios = await apiRequest(`/folios/reservation/${resId}`);
    const container = document.getElementById("split-folios-container");
    container.innerHTML = "";

    folios.forEach(f => {
      const isMaster = f.folio_type === "MASTER";
      const card = document.createElement("div");
      card.className = "bg-white border rounded-xl p-5 shadow-sm flex flex-col justify-between";
      
      let itemsList = "";
      (f.items || []).forEach(item => {
        const otherFolio = folios.find(other => other.id !== f.id);
        const splitBtn = otherFolio ? `
          <button onclick="splitFolioItem('${item.id}', '${otherFolio.id}')"
            class="text-[10px] bg-purple-50 text-purple-700 border border-purple-200 px-2 py-0.5 rounded font-semibold hover:bg-purple-100">
            Transfer to ${otherFolio.folio_type}
          </button>` : '';

        itemsList += `
          <li class="py-2 border-b flex justify-between items-center text-xs">
            <div>
              <div class="font-medium text-slate-900">${item.description}</div>
              <div class="text-[10px] text-slate-500">${item.category} • Tax: $${item.tax_amount.toFixed(2)}</div>
            </div>
            <div class="flex items-center space-x-2">
              <span class="font-bold text-slate-900">$${(item.amount + item.tax_amount).toFixed(2)}</span>
              ${splitBtn}
            </div>
          </li>
        `;
      });

      card.innerHTML = `
        <div>
          <div class="flex justify-between items-center mb-3">
            <div>
              <span class="text-xs font-bold uppercase tracking-wider ${isMaster ? 'text-sky-700' : 'text-purple-700'}">${f.folio_type} FOLIO</span>
              <h4 class="text-sm font-extrabold text-slate-900">${f.payer_name}</h4>
            </div>
            <span class="text-xs px-2 py-0.5 rounded-full font-bold ${f.status === 'SETTLED' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">
              ${f.status}
            </span>
          </div>
          <ul class="divide-y mb-4 max-h-56 overflow-y-auto">
            ${itemsList || '<li class="py-4 text-center text-xs text-slate-400">No items charged yet</li>'}
          </ul>
        </div>
        <div class="border-t pt-3">
          <div class="flex justify-between text-xs mb-1">
            <span class="text-slate-500">Total Charges:</span>
            <span class="font-semibold">$${f.total_charges.toFixed(2)}</span>
          </div>
          <div class="flex justify-between text-xs mb-2">
            <span class="text-slate-500">Payments:</span>
            <span class="font-semibold text-emerald-600">-$${f.total_payments.toFixed(2)}</span>
          </div>
          <div class="flex justify-between text-sm font-bold border-t pt-1 mb-3">
            <span>Balance:</span>
            <span class="${f.balance > 0 ? 'text-rose-600' : 'text-emerald-600'}">$${f.balance.toFixed(2)}</span>
          </div>
          <div class="flex gap-2">
            <button onclick="openPostChargeModal('${f.id}', '${f.folio_type}')" class="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold py-2 rounded">
              + Post Charge
            </button>
            ${f.balance > 0 ? `
              <button onclick="settleFolioPayment('${f.id}', ${f.balance})" class="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold py-2 rounded">
                Settle $${f.balance.toFixed(2)}
              </button>` : ''}
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  } catch (e) {}
}

async function splitFolioItem(itemId, targetFolioId) {
  try {
    await apiRequest("/folios/split-item", "POST", { item_id: itemId, target_folio_id: targetFolioId });
    showToast("Charge item moved between folios", "success");
    refreshActiveFolio();
  } catch (e) {}
}

function openPostChargeModal(folioId, folioType) {
  document.getElementById("charge-modal-folio-id").value = folioId;
  document.getElementById("charge-modal-folio-type").innerText = folioType;
  document.getElementById("charge-modal").classList.remove("hidden");
}

function closePostChargeModal() {
  document.getElementById("charge-modal").classList.add("hidden");
}

async function submitPostCharge() {
  const folioId = document.getElementById("charge-modal-folio-id").value;
  const category = document.getElementById("charge-modal-cat").value;
  const desc = document.getElementById("charge-modal-desc").value.trim();
  const amount = parseFloat(document.getElementById("charge-modal-amt").value) || 0.0;

  if (!desc || amount <= 0) {
    showToast("Please enter valid item description and positive amount", "warning");
    return;
  }

  try {
    await apiRequest("/folios/post-charge", "POST", {
      folio_id: folioId,
      category: category,
      description: desc,
      amount: amount,
      tax_rate: 0.10
    });
    closePostChargeModal();
    showToast("Incidental charge posted successfully", "success");
    refreshActiveFolio();
  } catch (e) {}
}

async function settleFolioPayment(folioId, amount) {
  try {
    await apiRequest("/folios/pay", "POST", {
      folio_id: folioId,
      amount: amount,
      card_token: "tok_pci_visa_split_settlement",
      transaction_type: "CAPTURE"
    });
    showToast(`Folio settled! $${amount.toFixed(2)} captured.`, "success");
    refreshActiveFolio();
  } catch (e) {}
}

// --- Night Audit ---
async function loadNightAuditChecklist() {
  try {
    const check = await apiRequest(`/night-audit/checklist?property_id=${state.propertyId}`);
    document.getElementById("audit-business-date").innerText = check.current_business_date;
    document.getElementById("audit-pending-arrivals").innerText = check.pending_arrivals_count;
    document.getElementById("audit-in-house").innerText = check.in_house_reservations_count;
    document.getElementById("audit-overdue-departures").innerText = check.overdue_departures_count;
  } catch (e) {}
}

async function executeNightAudit() {
  if (!confirm("Are you sure you want to run the End-of-Day Night Audit? This will post all nightly room charges, reconcile revenues, generate ERP journals, and advance the business date.")) {
    return;
  }
  try {
    const res = await apiRequest("/night-audit/execute", "POST", { property_id: state.propertyId });
    showToast(res.message, "success");

    // Display summary modal
    document.getElementById("audit-result-closed-date").innerText = res.closed_business_date;
    document.getElementById("audit-result-new-date").innerText = res.new_business_date;
    document.getElementById("audit-result-occ").innerText = `${res.occupancy_rate}% (${res.total_rooms_occupied} rooms)`;
    document.getElementById("audit-result-rev").innerText = `$${res.total_room_revenue.toFixed(2)}`;
    document.getElementById("audit-result-tax").innerText = `$${res.total_tax_revenue.toFixed(2)}`;
    document.getElementById("audit-result-inc").innerText = `$${res.total_incidental_revenue.toFixed(2)}`;

    // Set export download links
    document.getElementById("btn-download-netsuite").onclick = () => {
      window.open(`${API_BASE}/night-audit/export/netsuite/${res.audit_record_id}`, "_blank");
    };
    document.getElementById("btn-download-qb").onclick = () => {
      window.open(`${API_BASE}/night-audit/export/quickbooks/${res.audit_record_id}`, "_blank");
    };

    document.getElementById("audit-result-modal").classList.remove("hidden");
    loadNightAuditChecklist();
  } catch (e) {}
}

function closeAuditResultModal() {
  document.getElementById("audit-result-modal").classList.add("hidden");
}

// --- Compliance & Tamper-Evident Audit Ledger ---
async function loadAuditLedger() {
  try {
    const rows = await apiRequest("/compliance/audit-ledger?limit=40");
    const tbody = document.getElementById("audit-ledger-tbody");
    tbody.innerHTML = "";

    rows.forEach(r => {
      const tr = document.createElement("tr");
      tr.className = "border-b text-xs hover:bg-slate-50";
      tr.innerHTML = `
        <td class="py-2.5 font-bold text-slate-800">#${r.id}</td>
        <td class="py-2.5 font-semibold text-sky-700">${r.action}</td>
        <td class="py-2.5">${r.user_role || 'System'}</td>
        <td class="py-2.5">${r.entity_type} (${r.entity_id.slice(0, 8)}...)</td>
        <td class="py-2.5 font-mono text-[10px] text-slate-400" title="${r.record_hash}">${r.record_hash.slice(0, 16)}...</td>
        <td class="py-2.5 text-slate-500">${new Date(r.created_at).toLocaleTimeString()}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {}
}

async function verifyLedgerIntegrity() {
  try {
    const res = await apiRequest("/compliance/audit-ledger/verify-integrity");
    const banner = document.getElementById("integrity-badge");
    banner.classList.remove("hidden");
    if (res.valid) {
      banner.className = "p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center space-x-2";
      banner.innerHTML = `<span>🛡️ Cryptographic SHA-256 Hash Chain Validated: ${res.total_records} immutable blocks verified with zero tampering.</span>`;
    } else {
      banner.className = "p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs font-semibold flex items-center space-x-2";
      banner.innerHTML = `<span>⚠️ Tampering Detected at Block #${res.tampered_id}! ${res.reason}</span>`;
    }
  } catch (e) {}
}

// --- Initialization ---
document.addEventListener("DOMContentLoaded", () => {
  // Set default search dates
  const today = new Date();
  const next3Days = new Date(today);
  next3Days.setDate(today.getDate() + 3);

  document.getElementById("search-checkin").value = today.toISOString().split("T")[0];
  document.getElementById("search-checkout").value = next3Days.toISOString().split("T")[0];

  switchMainTab("guest-booking");
});

