/**
 * ShadowChat Web Terminal Engine
 */
const state = {
  token: localStorage.getItem('shadow_token') || null,
  username: localStorage.getItem('shadow_username') || null,
  activeRooms: {}, // room_id -> {room_id, peer, session_key_hex}
  pendingInvites: [],
  ws: null,
  inputMode: 'menu', // 'menu', 'register_email', 'register_otp', 'register_user', 'register_pass', 'login_user', 'login_pass', 'search_user', 'invite_confirm'
  tempData: {},
};

const output = document.getElementById('output-log');
const input = document.getElementById('terminal-input');
const prefix = document.getElementById('prompt-prefix');
const terminalBody = document.getElementById('terminal-body');

function scrollBottom() {
  terminalBody.scrollTop = terminalBody.scrollHeight;
}

function print(text, cls = '') {
  const line = document.createElement('div');
  line.className = `log-line ${cls}`;
  line.textContent = text;
  output.appendChild(line);
  scrollBottom();
}

function printHTML(html) {
  const line = document.createElement('div');
  line.className = 'log-line';
  line.innerHTML = html;
  output.appendChild(line);
  scrollBottom();
}

// Focus input on click anywhere inside terminal
document.addEventListener('click', () => {
  input.focus();
});

// API Helpers
async function apiPost(endpoint, data) {
  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const json = await res.json();
  if (!res.ok) {
    throw new Error(json.detail || 'Request failed');
  }
  return json;
}

async function apiGet(endpoint) {
  const res = await fetch(endpoint);
  const json = await res.json();
  if (!res.ok) {
    throw new Error(json.detail || 'Request failed');
  }
  return json;
}

// WebSocket Connection
function connectWebSocket() {
  if (!state.token) return;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws?token=${encodeURIComponent(state.token)}`;

  state.ws = new WebSocket(wsUrl);

  state.ws.onopen = () => {
    document.getElementById('conn-status').textContent = 'ONLINE';
    document.getElementById('conn-status').style.color = '#4ade80';
  };

  state.ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWsMessage(msg);
    } catch (e) {
      console.error('WS Parse Error', e);
    }
  };

  state.ws.onclose = () => {
    document.getElementById('conn-status').textContent = 'DISCONNECTED';
    document.getElementById('conn-status').style.color = '#f87171';
    setTimeout(connectWebSocket, 3000);
  };
}

function handleWsMessage(msg) {
  const mtype = msg.type;
  if (mtype === 'invitation_received') {
    print(`\n>> [ALERT] New chat request from @${msg.from}!`, 'yellow bold');
    print(`Type '2' or 'invites' to review and accept.\n`, 'dim');
  } else if (mtype === 'invitation_cancelled') {
    print(`\n>> A chat request was cancelled by sender.`, 'dim');
  } else if (mtype === 'invitation_rejected') {
    print(`\n>> @${msg.by} declined your chat request.`, 'red');
  } else if (mtype === 'invitation_expired' || mtype === 'invitation_expired_sender') {
    print(`\n>> A chat request expired.`, 'dim');
  } else if (mtype === 'room_active') {
    const peer = msg.peer;
    const roomId = msg.room_id;
    const keyHex = msg.session_key;
    state.activeRooms[roomId] = { room_id: roomId, peer: peer, session_key_hex: keyHex };

    print(`\n>> [ACTIVE] Private conversation with @${peer} established!`, 'green bold');
    print(`>> Opening separate conversation window...\n`, 'cyan');

    openChatWindow(roomId, peer, keyHex);
  } else if (mtype === 'room_terminated') {
    const rid = msg.room_id;
    if (rid) delete state.activeRooms[rid];
    print(`\n>> Conversation ended: ${msg.reason || 'Room terminated'}`, 'red');
  }
}

// Spawns dedicated popup chat window
function openChatWindow(roomId, peer, sessionKeyHex) {
  const url = `/chat?room_id=${encodeURIComponent(roomId)}&peer=${encodeURIComponent(peer)}&session_key=${encodeURIComponent(sessionKeyHex)}&username=${encodeURIComponent(state.username)}&token=${encodeURIComponent(state.token)}`;
  
  // Try popup window first
  const w = 750;
  const h = 550;
  const left = (screen.width / 2) - (w / 2);
  const top = (screen.height / 2) - (h / 2);

  const win = window.open(
    url,
    `Terminal_@${peer}`,
    `toolbar=no, location=no, directories=no, status=no, menubar=no, scrollbars=no, resizable=yes, copyhistory=no, width=${w}, height=${h}, top=${top}, left=${left}`
  );

  if (!win || win.closed || typeof win.closed === 'undefined') {
    // Popup was blocked by browser, open in new tab
    window.open(url, '_blank');
  }
}

// Menu displays
function showMainMenu() {
  state.inputMode = 'menu';
  prefix.textContent = 'shadowchat:~$';
  input.type = 'text';

  if (!state.token) {
    printHTML(`
      <div class="menu-box">
        <div class="menu-title">SHADOWCHAT // AUTHENTICATION</div>
        <div class="menu-item"><span>[1]</span> Register (Gmail OTP Verification)</div>
        <div class="menu-item"><span>[2]</span> Login</div>
        <div class="menu-item"><span>[3]</span> Help</div>
      </div>
    `);
    print('Select option (1-3):', 'dim');
  } else {
    const activePeers = Object.values(state.activeRooms).map(r => `@${r.peer}`).join(', ') || 'None';
    printHTML(`
      <div class="menu-box">
        <div class="menu-title">DASHBOARD - Logged in as: @${state.username}</div>
        <div class="menu-item"><span>[1]</span> Search User (Check online status & send invite)</div>
        <div class="menu-item"><span>[2]</span> Notifications & Pending Invites</div>
        <div class="menu-item"><span>[3]</span> Active Chats (${activePeers})</div>
        <div class="menu-item"><span>[4]</span> Help</div>
        <div class="menu-item"><span>[5]</span> Logout</div>
      </div>
    `);
    print('Select option (1-5) or type command:', 'dim');
  }
}

// Command execution
async function handleInput(val) {
  const text = val.trim();
  if (!text && state.inputMode === 'menu') return;

  // Echo user command
  print(`${prefix.textContent} ${input.type === 'password' ? '••••••••' : text}`, 'cyan');
  input.value = '';

  try {
    switch (state.inputMode) {
      case 'menu':
        await handleMenuCommand(text);
        break;

      case 'register_email':
        state.tempData.email = text;
        print(`Sending verification code to ${text}...`, 'dim');
        try {
          await apiPost('/register/start', { email: text });
          print(`[✓] Verification code sent! Check your inbox.`, 'green');
          print(`Enter the 6-digit OTP code:`, 'yellow');
          state.inputMode = 'register_otp';
          prefix.textContent = 'otp:~$';
        } catch (e) {
          print(`[x] ${e.message}`, 'red');
          showMainMenu();
        }
        break;

      case 'register_otp':
        print(`Verifying OTP...`, 'dim');
        try {
          const res = await apiPost('/register/verify', { email: state.tempData.email, otp: text });
          state.tempData.verificationToken = res.verification_token;
          print(`[✓] Email verified successfully!`, 'green');
          print(`Choose your unique Username:`, 'yellow');
          state.inputMode = 'register_user';
          prefix.textContent = 'username:~$';
        } catch (e) {
          print(`[x] ${e.message}`, 'red');
          showMainMenu();
        }
        break;

      case 'register_user':
        state.tempData.username = text;
        print(`Choose a secure password:`, 'yellow');
        state.inputMode = 'register_pass';
        prefix.textContent = 'password:~$';
        input.type = 'password';
        break;

      case 'register_pass':
        print(`Creating account...`, 'dim');
        input.type = 'text';
        try {
          await apiPost('/register/complete', {
            verification_token: state.tempData.verificationToken,
            username: state.tempData.username,
            password: text,
          });
          print(`[✓] Account created successfully for @${state.tempData.username}!`, 'green bold');
          print(`You may now log in.\n`, 'cyan');
          showMainMenu();
        } catch (e) {
          print(`[x] ${e.message}`, 'red');
          showMainMenu();
        }
        break;

      case 'login_user':
        state.tempData.username = text;
        print(`Password:`, 'yellow');
        state.inputMode = 'login_pass';
        prefix.textContent = 'password:~$';
        input.type = 'password';
        break;

      case 'login_pass':
        input.type = 'text';
        print(`Authenticating...`, 'dim');
        try {
          const res = await apiPost('/login', {
            username: state.tempData.username,
            password: text,
          });
          state.token = res.token;
          state.username = res.username;
          localStorage.setItem('shadow_token', res.token);
          localStorage.setItem('shadow_username', res.username);
          print(`[✓] Welcome back, @${res.username}!`, 'green bold');
          connectWebSocket();
          showMainMenu();
        } catch (e) {
          print(`[x] ${e.message}`, 'red');
          showMainMenu();
        }
        break;

      case 'search_user':
        await doSearchUser(text);
        break;

      case 'invite_confirm':
        if (text === '1' || text.toLowerCase() === 'y' || text.toLowerCase() === 'yes') {
          await doSendInvite(state.tempData.targetUser);
        } else {
          print('Invitation cancelled.', 'dim');
          showMainMenu();
        }
        break;

      case 'select_invite':
        await handleInviteDecision(text);
        break;
    }
  } catch (err) {
    print(`[Error] ${err.message}`, 'red');
    showMainMenu();
  }
}

async function handleMenuCommand(cmd) {
  const c = cmd.toLowerCase();

  if (!state.token) {
    if (c === '1' || c === 'register') {
      state.inputMode = 'register_email';
      prefix.textContent = 'email:~$';
      print('Enter your Gmail address:', 'yellow');
    } else if (c === '2' || c === 'login') {
      state.inputMode = 'login_user';
      prefix.textContent = 'username:~$';
      print('Username:', 'yellow');
    } else if (c === '3' || c === 'help') {
      print('Register a new account or log in with your credentials.', 'dim');
      showMainMenu();
    } else {
      print(`Unknown command: ${cmd}`, 'red');
      showMainMenu();
    }
  } else {
    if (c === '1' || c === 'search') {
      state.inputMode = 'search_user';
      prefix.textContent = 'search:~$';
      print('Enter Username to search:', 'yellow');
    } else if (c === '2' || c === 'invites' || c === 'notifications') {
      await showNotifications();
    } else if (c === '3' || c === 'active') {
      showActiveChats();
    } else if (c === '4' || c === 'help') {
      printHTML(`
        <div class="menu-box">
          <div class="menu-title">COMMAND REFERENCE</div>
          <div class="menu-item"><span>search &lt;user&gt;</span> - Look up user and send chat invite</div>
          <div class="menu-item"><span>invites</span> - View and accept pending chat requests</div>
          <div class="menu-item"><span>active</span> - Re-open active chat windows</div>
          <div class="menu-item"><span>logout</span> - Terminate local session</div>
        </div>
      `);
      showMainMenu();
    } else if (c === '5' || c === 'logout') {
      localStorage.removeItem('shadow_token');
      localStorage.removeItem('shadow_username');
      state.token = null;
      state.username = null;
      if (state.ws) state.ws.close();
      print('[✓] Logged out successfully.\n', 'green');
      showMainMenu();
    } else if (c.startsWith('search ')) {
      const q = c.split(' ')[1];
      if (q) await doSearchUser(q);
    } else {
      print(`Unknown command: ${cmd}. Type 'help' for options.`, 'red');
      showMainMenu();
    }
  }
}

async function doSearchUser(query) {
  print(`Searching for user @${query}...`, 'dim');
  try {
    const res = await apiGet(`/search?query=${encodeURIComponent(query)}&token=${encodeURIComponent(state.token)}`);
    print(`[✓] USER FOUND: @${res.user_id} (${res.status})`, 'green bold');
    state.tempData.targetUser = res.user_id;
    print(`Request private chat? [1] YES  [2] NO:`, 'yellow');
    state.inputMode = 'invite_confirm';
    prefix.textContent = 'confirm:~$';
  } catch (e) {
    print(`[x] ${e.message}`, 'red');
    showMainMenu();
  }
}

async function doSendInvite(username) {
  print(`Sending invitation to @${username}...`, 'dim');
  try {
    await apiPost('/invite', { token: state.token, receiver_username: username });
    print(`[✓] Invitation sent to @${username}! Waiting for recipient to accept...`, 'green');
    print(`When accepted, a separate conversation window will automatically open.\n`, 'cyan');
    showMainMenu();
  } catch (e) {
    print(`[x] ${e.message}`, 'red');
    showMainMenu();
  }
}

async function showNotifications() {
  print(`Fetching pending requests...`, 'dim');
  try {
    const res = await apiGet(`/invitations?token=${encodeURIComponent(state.token)}`);
    const invites = res.invitations || [];
    state.pendingInvites = invites;

    if (invites.length === 0) {
      print('No pending chat requests.', 'dim');
      showMainMenu();
      return;
    }

    printHTML(`
      <div class="menu-box">
        <div class="menu-title">PENDING CHAT REQUESTS</div>
        ${invites.map((inv, idx) => `<div class="menu-item"><span>[${idx + 1}]</span> From: <b>@${inv.from}</b> (${inv.status})</div>`).join('')}
      </div>
    `);

    print(`Select invitation # to respond (0 to cancel):`, 'yellow');
    state.inputMode = 'select_invite';
    prefix.textContent = 'select:~$';
  } catch (e) {
    print(`[x] ${e.message}`, 'red');
    showMainMenu();
  }
}

async function handleInviteDecision(text) {
  const idx = parseInt(text, 10);
  if (isNaN(idx) || idx === 0 || idx > state.pendingInvites.length) {
    showMainMenu();
    return;
  }

  const selected = state.pendingInvites[idx - 1];
  print(`Accept chat request from @${selected.from}? [1] ACCEPT  [2] REJECT:`, 'yellow');
  state.tempData.selectedInvite = selected;
  state.inputMode = 'accept_or_reject';
  prefix.textContent = 'action:~$';
}

input.addEventListener('keydown', async (e) => {
  if (e.key === 'Enter') {
    const val = input.value;
    if (state.inputMode === 'accept_or_reject') {
      const choice = val.trim();
      input.value = '';
      const accept = choice === '1';
      print(`Responding to invitation...`, 'dim');
      try {
        const res = await apiPost('/invitations/respond', {
          token: state.token,
          invitation_id: state.tempData.selectedInvite.invitation_id,
          accept: accept,
        });
        if (accept) {
          print(`[✓] Joined room with @${res.peer}!`, 'green bold');
        } else {
          print(`Invitation declined.`, 'dim');
        }
        showMainMenu();
      } catch (err) {
        print(`[x] ${err.message}`, 'red');
        showMainMenu();
      }
      return;
    }

    await handleInput(val);
  }
});

function showActiveChats() {
  const rooms = Object.values(state.activeRooms);
  if (rooms.length === 0) {
    print('No active conversations found.', 'dim');
    showMainMenu();
    return;
  }

  printHTML(`
    <div class="menu-box">
      <div class="menu-title">ACTIVE CONVERSATIONS</div>
      ${rooms.map((r, i) => `<div class="menu-item"><span>[${i + 1}]</span> @${r.peer} (Click to open window)</div>`).join('')}
    </div>
  `);

  rooms.forEach(r => openChatWindow(r.room_id, r.peer, r.session_key_hex));
  showMainMenu();
}

// Boot up
if (state.token) {
  connectWebSocket();
}
showMainMenu();
