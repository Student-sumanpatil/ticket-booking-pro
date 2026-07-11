const state = {
    token: localStorage.getItem('token') || null,
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    selectedSeats: new Set(),
    seatMapPoll: null,
    events: [],
};

function saveAuth(token, user) {
    state.token = token; state.user = user;
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
}
function logout() {
    state.token = null; state.user = null;
    localStorage.removeItem('token'); localStorage.removeItem('user');
    navigate('events');
}

async function api(path, options = {}) {
    const headers = options.headers || {};
    headers['Content-Type'] = 'application/json';
    if (state.token) headers['Authorization'] = 'Bearer ' + state.token;
    const res = await fetch(path, { ...options, headers });
    let data = null;
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) throw new Error((data && data.detail) || 'Something went wrong');
    return data;
}

function renderNav() {
    const nav = document.getElementById('nav');
    if (!state.user) {
        nav.innerHTML = `<a onclick="navigate('events')">Movies</a><a onclick="navigate('login')">Log in</a><a onclick="navigate('register')">Sign up</a>`;
        return;
    }
    let extra = '';
    if (state.user.role === 'organiser') extra = `<a onclick="navigate('organiser')">Dashboard</a>`;
    if (state.user.role === 'admin') extra = `<a onclick="navigate('admin')">Venues</a>`;
    nav.innerHTML = `
        <a onclick="navigate('events')">Movies</a>
        ${state.user.role === 'customer' ? `<a onclick="navigate('mybookings')">My Tickets</a>` : ''}
        ${extra}
        <span class="role-badge">${state.user.role}</span>
        <button onclick="logout()">Log out</button>`;
}

function flash(msg, type = 'error') {
    return `<div class="flash flash-${type}">${msg}</div>`;
}

// ---------------- Router ----------------
function navigate(view, params = {}) {
    if (state.seatMapPoll) { clearInterval(state.seatMapPoll); state.seatMapPoll = null; }
    renderNav();
    const app = document.getElementById('app');
    const views = {
        events: renderEvents, login: renderLogin, register: renderRegister,
        show: renderShow, mybookings: renderMyBookings,
        organiser: renderOrganiser, admin: renderAdmin,
    };
    (views[view] || renderEvents)(app, params);
}

// ---------------- Auth views ----------------
function renderLogin(app) {
    app.innerHTML = `
    <div class="card" style="max-width:380px;margin:40px auto;">
        <h2>Log in</h2>
        <div id="msg"></div>
        <form id="f">
            <label>Email <input type="email" name="email" required></label>
            <label>Password <input type="password" name="password" required></label>
            <button class="btn btn-primary" style="width:100%">Log in</button>
        </form>
        <p class="subdued" style="margin-top:14px;">No account? <a style="color:var(--gold)" onclick="navigate('register')">Sign up</a></p>
    </div>`;
    document.getElementById('f').onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
            const data = await api('/api/auth/login', { method: 'POST', body: JSON.stringify(Object.fromEntries(fd)) });
            saveAuth(data.access_token, data.user);
            navigate('events');
        } catch (err) { document.getElementById('msg').innerHTML = flash(err.message); }
    };
}

function renderRegister(app) {
    app.innerHTML = `
    <div class="card" style="max-width:420px;margin:40px auto;">
        <h2>Create your account</h2>
        <div id="msg"></div>
        <form id="f">
            <label>Full name <input type="text" name="name" required></label>
            <label>Email <input type="email" name="email" required></label>
            <label>Password (min 6 chars) <input type="password" name="password" minlength="6" required></label>
            <label>Account type
                <select name="role">
                    <option value="customer">Customer - browse and book</option>
                    <option value="organiser">Organiser - list events</option>
                    <option value="admin">Admin - manage venues</option>
                </select>
            </label>
            <button class="btn btn-primary" style="width:100%">Sign up</button>
        </form>
    </div>`;
    document.getElementById('f').onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
            const data = await api('/api/auth/register', { method: 'POST', body: JSON.stringify(Object.fromEntries(fd)) });
            saveAuth(data.access_token, data.user);
            navigate('events');
        } catch (err) { document.getElementById('msg').innerHTML = flash(err.message); }
    };
}

// ---------------- Events / shows ----------------
async function renderEvents(app) {
    app.innerHTML = `<p class="eyebrow">Now booking</p><h1>Pick a film, pick a seat</h1><div id="list" class="grid grid-cards" style="margin-top:24px;">Loading...</div>`;
    try {
        const events = await api('/api/events');
        state.events = events;
        const list = document.getElementById('list');
        if (!events.length) { list.innerHTML = `<p class="subdued">No events yet.</p>`; return; }
        list.innerHTML = events.map(e => `
            <div class="card event-card" onclick='openEvent(${e.id})'>
                <p class="eyebrow">${e.genre}</p>
                <h3>${e.title}</h3>
                <p class="subdued">${e.description.slice(0, 90)}${e.description.length > 90 ? '…' : ''}</p>
                <p class="subdued">${e.shows.length} showtime(s)</p>
            </div>`).join('');
    } catch (err) { document.getElementById('list').innerHTML = flash(err.message); }
}

function openEvent(eventId) {
    const event = state.events.find(e => e.id === eventId);
    if (!event.shows.length) return;
    navigate('show', { event, showId: event.shows[0].id });
}

async function renderShow(app, { event, showId }) {
    if (!state.user) { navigate('login'); return; }
    const show = event.shows.find(s => s.id === showId);
    app.innerHTML = `
    <a class="subdued" onclick="navigate('events')" style="cursor:pointer">&larr; All movies</a>
    <p class="eyebrow" style="margin-top:16px">${event.genre}</p>
    <h1>${event.title}</h1>
    <p class="subdued">${event.description}</p>
    <h2 style="margin-top:24px">Showtimes</h2>
    <div id="showtimes">${event.shows.map(s => `<span class="show-pill ${s.id === showId ? 'active' : ''}" onclick='navigate("show",{event: ${JSON.stringify(event).replace(/'/g, "&apos;")}, showId: ${s.id}})'>
        <span class="subdued">${s.date}</span><strong>${s.time}</strong><span class="subdued">${s.venue}</span></span>`).join('')}</div>
    <div id="msg" style="margin-top:16px"></div>
    <div class="grid grid-2" style="margin-top:20px;align-items:start;">
        <div class="card">
            <h3>Select your seats</h3>
            <div id="seatmap" class="seat-map">Loading seat map…</div>
            <div class="legend">
                <span><i style="background:var(--surface-raised);border:1px solid var(--border)"></i>Available</span>
                <span><i style="background:var(--red)"></i>Selected</span>
                <span><i style="background:#3a341a"></i>Held by others</span>
                <span><i style="background:#26262b"></i>Booked</span>
            </div>
        </div>
        <div class="card">
            <h3>Your selection</h3>
            <p id="selection-summary" class="subdued">No seats selected</p>
            <button class="btn btn-primary" id="hold-btn" style="width:100%;margin-top:10px" disabled>Hold seats (${window.HOLD_TTL || 10} min)</button>
            <div id="hold-panel" style="margin-top:16px"></div>
            <hr style="border-color:var(--border);margin:16px 0">
            <h3>Sold out for your category?</h3>
            <label>Category <select id="wl-category"></select></label>
            <button class="btn" id="wl-btn" style="width:100%">Join waitlist</button>
        </div>
    </div>`;

    state.selectedSeats = new Set();
    await loadSeatMap(showId);
    state.seatMapPoll = setInterval(() => loadSeatMap(showId), 4000);

    document.getElementById('hold-btn').onclick = () => placeHold(showId);
    document.getElementById('wl-btn').onclick = () => joinWaitlist(showId);
}

let seatMapCache = [];

async function loadSeatMap(showId) {
    try {
        const seats = await api(`/api/shows/${showId}/seatmap`);
        seatMapCache = seats;
        const container = document.getElementById('seatmap');
        if (!container) return; // navigated away

        const byRow = {};
        seats.forEach(s => { const row = s.label.match(/^[A-Za-z]+/)[0]; (byRow[row] = byRow[row] || []).push(s); });

        container.innerHTML = Object.keys(byRow).sort().map(row => `
            <div class="seat-row"><span class="row-label">${row}</span>
            ${byRow[row].sort((a, b) => parseInt(a.label.slice(row.length)) - parseInt(b.label.slice(row.length))).map(s => {
                let cls = 'available';
                if (s.status === 'booked') cls = 'booked';
                else if (s.status === 'held') cls = s.held_by_me ? 'held-by-me' : 'held';
                if (state.selectedSeats.has(s.label) && s.status === 'available') cls = 'selected';
                const clickable = s.status === 'available';
                return `<span class="seat ${cls}" ${clickable ? `onclick="toggleSeat('${s.label}')"` : ''} title="${s.label} · ${s.category} · ₹${s.price}">${s.label.replace(/^[A-Za-z]+/, '')}</span>`;
            }).join('')}</div>`).join('');

        const categories = [...new Set(seats.map(s => s.category))];
        const catSelect = document.getElementById('wl-category');
        if (catSelect && !catSelect.dataset.loaded) {
            catSelect.innerHTML = categories.map(c => `<option value="${c}">${c}</option>`).join('');
            catSelect.dataset.loaded = '1';
        }
        updateSelectionSummary();
    } catch (err) {
        console.error(err);
    }
}

function toggleSeat(label) {
    if (state.selectedSeats.has(label)) state.selectedSeats.delete(label);
    else state.selectedSeats.add(label);
    repaintFromCache();
}

function repaintFromCache() {
    const container = document.getElementById('seatmap');
    if (!container || !seatMapCache.length) return;
    const byRow = {};
    seatMapCache.forEach(s => { const row = s.label.match(/^[A-Za-z]+/)[0]; (byRow[row] = byRow[row] || []).push(s); });
    container.innerHTML = Object.keys(byRow).sort().map(row => `
        <div class="seat-row"><span class="row-label">${row}</span>
        ${byRow[row].sort((a, b) => parseInt(a.label.slice(row.length)) - parseInt(b.label.slice(row.length))).map(s => {
            let cls = 'available';
            if (s.status === 'booked') cls = 'booked';
            else if (s.status === 'held') cls = s.held_by_me ? 'held-by-me' : 'held';
            if (state.selectedSeats.has(s.label) && s.status === 'available') cls = 'selected';
            const clickable = s.status === 'available';
            return `<span class="seat ${cls}" ${clickable ? `onclick="toggleSeat('${s.label}')"` : ''} title="${s.label} · ${s.category} · ₹${s.price}">${s.label.replace(/^[A-Za-z]+/, '')}</span>`;
        }).join('')}</div>`).join('');
    updateSelectionSummary();
}

function updateSelectionSummary() {
    const el = document.getElementById('selection-summary');
    const btn = document.getElementById('hold-btn');
    if (!el) return;
    if (!state.selectedSeats.size) { el.textContent = 'No seats selected'; btn.disabled = true; return; }
    const labels = [...state.selectedSeats];
    const total = labels.reduce((sum, l) => {
        const s = seatMapCache.find(x => x.label === l);
        return sum + (s ? s.price : 0);
    }, 0);
    el.innerHTML = `Seats: <strong>${labels.join(', ')}</strong><br>Total: <strong>₹${total}</strong>`;
    btn.disabled = false;
}

async function placeHold(showId) {
    const panel = document.getElementById('hold-panel');
    try {
        const hold = await api('/api/holds', {
            method: 'POST',
            body: JSON.stringify({ show_id: showId, seat_labels: [...state.selectedSeats] }),
        });
        let secondsLeft = Math.round((new Date(hold.expires_at + 'Z') - new Date()) / 1000);
        panel.innerHTML = `
            ${flash('Seats held for you. Confirm before the timer runs out.', 'success')}
            <p class="countdown" id="countdown">${secondsLeft}s</p>
            <button class="btn btn-primary" style="width:100%" onclick="confirmBooking('${hold.hold_token}')">Confirm booking - ₹${hold.total_price}</button>`;
        const timer = setInterval(() => {
            secondsLeft--;
            const el = document.getElementById('countdown');
            if (!el) { clearInterval(timer); return; }
            if (secondsLeft <= 0) { el.textContent = 'Expired'; clearInterval(timer); loadSeatMap(showId); return; }
            el.textContent = secondsLeft + 's';
        }, 1000);
    } catch (err) {
        panel.innerHTML = flash(err.message);
        loadSeatMap(showId);
    }
}

async function confirmBooking(holdToken) {
    const panel = document.getElementById('hold-panel');
    try {
        const booking = await api('/api/bookings', { method: 'POST', body: JSON.stringify({ hold_token: holdToken }) });
        panel.innerHTML = flash(`Booked! Reference <strong>${booking.booking_reference}</strong>. A confirmation email (with QR ticket) was sent - check My Tickets.`, 'success');
        state.selectedSeats = new Set();
    } catch (err) {
        panel.innerHTML = flash(err.message);
    }
}

async function joinWaitlist(showId) {
    const category = document.getElementById('wl-category').value;
    const msg = document.getElementById('msg');
    try {
        await api('/api/waitlist', { method: 'POST', body: JSON.stringify({ show_id: showId, category_name: category }) });
        msg.innerHTML = flash(`Added to the ${category} waitlist. We'll email you if a seat opens up.`, 'success');
    } catch (err) { msg.innerHTML = flash(err.message); }
}

// ---------------- My bookings ----------------
async function renderMyBookings(app) {
    if (!state.user) { navigate('login'); return; }
    app.innerHTML = `<h1>My tickets</h1><div id="list">Loading…</div>`;
    try {
        const bookings = await api('/api/bookings/me');
        const list = document.getElementById('list');
        if (!bookings.length) { list.innerHTML = `<p class="subdued">No bookings yet.</p>`; return; }
        list.innerHTML = bookings.map(b => `
            <div class="card" style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <h3>${b.booking_reference}</h3>
                    <p class="subdued">Seats: ${b.seat_labels} &middot; ₹${b.total_price}</p>
                </div>
                <div style="text-align:right">
                    <span class="tag tag-${b.status}">${b.status}</span><br>
                    ${b.status === 'confirmed' ? `<button class="btn btn-sm" style="margin-top:8px" onclick="cancelBooking(${b.id})">Cancel</button>` : ''}
                </div>
            </div>`).join('');
    } catch (err) { document.getElementById('list').innerHTML = flash(err.message); }
}

async function cancelBooking(id) {
    try { await api(`/api/bookings/${id}/cancel`, { method: 'POST' }); renderMyBookings(document.getElementById('app')); }
    catch (err) { alert(err.message); }
}

// ---------------- Organiser dashboard ----------------
async function renderOrganiser(app) {
    if (!state.user || state.user.role !== 'organiser') { navigate('events'); return; }
    app.innerHTML = `
    <h1>Organiser dashboard</h1>
    <div class="grid grid-2">
        <div class="card">
            <h3>Create an event</h3>
            <div id="event-msg"></div>
            <form id="event-form">
                <label>Title <input name="title" required></label>
                <label>Genre <input name="genre" required></label>
                <label>Description <textarea name="description" rows="3" required></textarea></label>
                <button class="btn btn-primary">Create event</button>
            </form>
        </div>
        <div class="card">
            <h3>Schedule a show</h3>
            <p class="subdued">Needs an event ID (shown after creating one) and a venue ID (from the admin dashboard).</p>
            <div id="show-msg"></div>
            <form id="show-form">
                <label>Event ID <input name="event_id" type="number" required></label>
                <label>Venue ID <input name="venue_id" type="number" required></label>
                <label>Date <input name="show_date" type="date" required></label>
                <label>Time <input name="show_time" type="time" required></label>
                <label>Category prices (e.g. Premium:300, Standard:200) <input name="prices" placeholder="Premium:300, Standard:200" required></label>
                <button class="btn btn-primary">Create show</button>
            </form>
        </div>
    </div>
    <div class="card" style="margin-top:20px">
        <h3>Revenue lookup</h3>
        <form id="rev-form" style="display:flex;gap:10px;align-items:end;">
            <label style="flex:1">Event ID <input name="event_id" type="number" required></label>
            <button class="btn">Check revenue</button>
        </form>
        <div id="rev-out" style="margin-top:12px"></div>
    </div>`;

    document.getElementById('event-form').onsubmit = async (e) => {
        e.preventDefault();
        const fd = Object.fromEntries(new FormData(e.target));
        try {
            const ev = await api('/api/organiser/events', { method: 'POST', body: JSON.stringify(fd) });
            document.getElementById('event-msg').innerHTML = flash(`Created event ID ${ev.id} - "${ev.title}"`, 'success');
            e.target.reset();
        } catch (err) { document.getElementById('event-msg').innerHTML = flash(err.message); }
    };

    document.getElementById('show-form').onsubmit = async (e) => {
        e.preventDefault();
        const fd = Object.fromEntries(new FormData(e.target));
        const category_prices = fd.prices.split(',').map(p => {
            const [category_name, price] = p.split(':').map(x => x.trim());
            return { category_name, price: parseFloat(price) };
        });
        try {
            const show = await api('/api/organiser/shows', {
                method: 'POST',
                body: JSON.stringify({ event_id: parseInt(fd.event_id), venue_id: parseInt(fd.venue_id), show_date: fd.show_date, show_time: fd.show_time, category_prices }),
            });
            document.getElementById('show-msg').innerHTML = flash(`Show scheduled (ID ${show.id})`, 'success');
            e.target.reset();
        } catch (err) { document.getElementById('show-msg').innerHTML = flash(err.message); }
    };

    document.getElementById('rev-form').onsubmit = async (e) => {
        e.preventDefault();
        const fd = Object.fromEntries(new FormData(e.target));
        try {
            const rev = await api(`/api/organiser/events/${fd.event_id}/revenue`);
            document.getElementById('rev-out').innerHTML = `
                <table><tr><th>Event</th><td>${rev.event}</td></tr>
                <tr><th>Shows</th><td>${rev.shows}</td></tr>
                <tr><th>Confirmed bookings</th><td>${rev.confirmed_bookings}</td></tr>
                <tr><th>Seats sold</th><td>${rev.seats_sold}</td></tr>
                <tr><th>Total revenue</th><td>₹${rev.total_revenue}</td></tr></table>`;
        } catch (err) { document.getElementById('rev-out').innerHTML = flash(err.message); }
    };
}

// ---------------- Admin dashboard ----------------
async function renderAdmin(app) {
    if (!state.user || state.user.role !== 'admin') { navigate('events'); return; }
    app.innerHTML = `
    <h1>Admin - venues</h1>
    <div class="card">
        <h3>Create a venue</h3>
        <p class="subdued">Define categories, then seats as rows × seats-per-row, each assigned a category.</p>
        <div id="msg"></div>
        <form id="f">
            <label>Venue name <input name="name" required></label>
            <label>Address <input name="address" required></label>
            <label>Categories (comma separated) <input name="categories" placeholder="Premium, Standard" required></label>
            <div class="grid grid-2">
                <label>Rows (e.g. A,B,C,D,E) <input name="rows" placeholder="A,B,C,D,E" required></label>
                <label>Seats per row <input name="per_row" type="number" value="8" required></label>
            </div>
            <label>Category for first N rows (rest use the 2nd category), N= <input name="premium_rows" type="number" value="2"></label>
            <button class="btn btn-primary">Create venue</button>
        </form>
    </div>`;

    document.getElementById('f').onsubmit = async (e) => {
        e.preventDefault();
        const fd = Object.fromEntries(new FormData(e.target));
        const categories = fd.categories.split(',').map(c => c.trim());
        const rows = fd.rows.split(',').map(r => r.trim());
        const perRow = parseInt(fd.per_row);
        const premiumRows = parseInt(fd.premium_rows || 0);
        const seats = [];
        rows.forEach((row, idx) => {
            const category_name = idx < premiumRows ? categories[0] : (categories[1] || categories[0]);
            for (let n = 1; n <= perRow; n++) seats.push({ row_label: row, seat_number: n, category_name });
        });
        try {
            const venue = await api('/api/admin/venues', {
                method: 'POST',
                body: JSON.stringify({ name: fd.name, address: fd.address, seat_categories: categories.map(name => ({ name })), seats }),
            });
            document.getElementById('msg').innerHTML = flash(`Venue created - ID ${venue.id}. Use this ID when scheduling shows.`, 'success');
            e.target.reset();
        } catch (err) { document.getElementById('msg').innerHTML = flash(err.message); }
    };
}

navigate('events');
