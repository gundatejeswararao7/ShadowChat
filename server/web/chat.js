/**
 * ShadowChat Dedicated Chat Window Engine
 * End-to-End Encrypted via Web Crypto API (AES-256-GCM)
 */

// Helper to convert hex to Uint8Array
function hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return bytes;
}

// Helper to convert Uint8Array to hex
function bytesToHex(bytes) {
  let s = '';
  for (let b of bytes) {
    s += b.toString(16).padStart(2, '0');
  }
  return s;
}

// Parse URL Parameters
const params = new URLSearchParams(window.location.search);
const roomId = params.get('room_id');
const peer = params.get('peer');
const sessionKeyHex = params.get('session_key');
const token = params.get('token');
const myUsername = params.get('username') || 'You';

// Update Window Titles
const windowTitle = `Terminal - @${peer}`;
document.title = windowTitle;
document.getElementById('page-title').textContent = windowTitle;
document.getElementById('chat-header-title').textContent = windowTitle;
document.getElementById('chat-peer-name').textContent = `@${peer}`;
document.getElementById('chat-my-name').textContent = myUsername;

const messagesDiv = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const chatBody = document.getElementById('chat-body');

let cryptoKey = null;
let ws = null;

function scrollBottom() {
  chatBody.scrollTop = chatBody.scrollHeight;
}

function appendMessage(sender, text, isSelf) {
  const line = document.createElement('div');
  line.className = 'msg-line';
  
  const senderSpan = document.createElement('span');
  senderSpan.className = `msg-sender ${isSelf ? 'self' : 'peer'}`;
  senderSpan.textContent = `${sender}:`;

  const contentSpan = document.createElement('span');
  contentSpan.className = 'msg-content';
  contentSpan.textContent = ` ${text}`;

  line.appendChild(senderSpan);
  line.appendChild(contentSpan);
  messagesDiv.appendChild(line);
  scrollBottom();
}

function appendSystemNotice(text, color = '#6b7280') {
  const line = document.createElement('div');
  line.style.color = color;
  line.style.fontSize = '12px';
  line.style.margin = '4px 0';
  line.textContent = `[${text}]`;
  messagesDiv.appendChild(line);
  scrollBottom();
}

// Initialize Web Crypto Key
async function initCrypto() {
  try {
    const rawKey = hexToBytes(sessionKeyHex);
    cryptoKey = await window.crypto.subtle.importKey(
      'raw',
      rawKey,
      { name: 'AES-GCM' },
      false,
      ['encrypt', 'decrypt']
    );
  } catch (err) {
    console.error('Crypto Init Error', err);
    appendSystemNotice('Cryptographic key import failed', '#f87171');
  }
}

// Encrypt plaintext with AES-256-GCM
async function encryptMessage(text) {
  const nonce = window.crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(text);
  const cipherBuffer = await window.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce },
    cryptoKey,
    encoded
  );
  return {
    nonce: bytesToHex(nonce),
    ciphertext: bytesToHex(new Uint8Array(cipherBuffer)),
  };
}

// Decrypt ciphertext with AES-256-GCM
async function decryptMessage(nonceHex, cipherHex) {
  const nonce = hexToBytes(nonceHex);
  const cipher = hexToBytes(cipherHex);
  const decBuffer = await window.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: nonce },
    cryptoKey,
    cipher
  );
  return new TextDecoder().decode(decBuffer);
}

// WebSocket Connection
function connectWs() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws?token=${encodeURIComponent(token)}`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    appendSystemNotice('Secure transport connected', '#4ade80');
  };

  ws.onmessage = async (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'chat_message') {
        if (msg.room_id && msg.room_id !== roomId) return;
        const sender = msg.from || peer;
        if (sender === myUsername) return; // Don't duplicate self

        try {
          const plain = await decryptMessage(msg.nonce, msg.ciphertext);
          appendMessage(sender, plain, false);
        } catch (e) {
          appendMessage(sender, '[Message could not be decrypted]', false);
        }
      } else if (msg.type === 'peer_disconnected') {
        appendSystemNotice(`@${peer} disconnected. Waiting for reconnection...`, '#facc15');
      } else if (msg.type === 'peer_reconnected') {
        appendSystemNotice(`@${peer} reconnected.`, '#4ade80');
      } else if (msg.type === 'room_terminated') {
        if (!msg.room_id || msg.room_id === roomId) {
          appendSystemNotice(`Room terminated: ${msg.reason || 'Conversation ended'}`, '#f87171');
          chatInput.disabled = true;
          chatInput.placeholder = 'Conversation ended. Close window.';
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  ws.onclose = () => {
    appendSystemNotice('Connection closed by server.', '#f87171');
  };
}

// Send Message
async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = '';

  if (text.toLowerCase() === '/leave') {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'leave_room', room_id: roomId }));
    }
    appendSystemNotice('You left the conversation.', '#6b7280');
    setTimeout(() => window.close(), 1000);
    return;
  }

  // Display locally as "You: message"
  appendMessage('You', text, true);

  try {
    const enc = await encryptMessage(text);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'chat_message',
        room_id: roomId,
        nonce: enc.nonce,
        ciphertext: enc.ciphertext,
      }));
    }
  } catch (err) {
    console.error('Send error', err);
    appendSystemNotice('Failed to encrypt or deliver message', '#f87171');
  }
}

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    sendMessage();
  }
});

// Auto focus
document.addEventListener('click', () => {
  chatInput.focus();
});

// Init
initCrypto().then(connectWs);
