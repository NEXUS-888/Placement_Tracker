const fs = require('fs');
const path = require('path');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');

// Load environment variables manually without extra npm package
function loadEnv() {
    const envPath = path.join(__dirname, '.env');
    if (!fs.existsSync(envPath)) return {};
    const lines = fs.readFileSync(envPath, 'utf8').split('\n');
    const env = {};
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const [k, ...v] = trimmed.split('=');
        if (k) env[k.trim()] = v.join('=').trim();
    }
    return env;
}

const env = loadEnv();
const PORT = process.env.PORT || env.PORT || 8000;
const TARGET_GROUP_KEYWORD = (process.env.TARGET_WHATSAPP_GROUP || env.TARGET_WHATSAPP_GROUP || 'placement').toLowerCase();
const WEBHOOK_URL = `http://127.0.0.1:${PORT}/api/webhook/incoming`;

const UPLOADS_DIR = path.join(__dirname, 'uploads');
if (!fs.existsSync(UPLOADS_DIR)) {
    fs.mkdirSync(UPLOADS_DIR, { recursive: true });
}

console.log('====================================================');
console.log('  Placement Tracker - WhatsApp Bridge (Read-Only)');
console.log('====================================================');
console.log(`[Bridge] Target group filter: "${TARGET_GROUP_KEYWORD}"`);
console.log(`[Bridge] Webhook endpoint   : ${WEBHOOK_URL}`);
console.log('[Bridge] Initializing WhatsApp Web Client...');

const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: path.join(__dirname, '.wwebjs_auth')
    }),
    puppeteer: {
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu'
        ]
    }
});

client.on('qr', (qr) => {
    console.log('\n[Bridge] 📱 QR Code received! Scan this QR code in WhatsApp > Linked Devices:');
    qrcode.generate(qr, { small: true });
    console.log('[Bridge] (You only need to scan this once! Future runs restore session automatically)\n');
});

client.on('authenticated', () => {
    console.log('[Bridge] ✅ Authenticated successfully! Session cached in .wwebjs_auth');
});

client.on('auth_failure', (msg) => {
    console.error('[Bridge] ❌ Authentication failure:', msg);
});

client.on('ready', () => {
    console.log('\n[Bridge] 🚀 WhatsApp Bridge is LIVE and listening for placement announcements!');
    console.log('[Bridge] Monitoring for incoming messages/files. Press Ctrl+C to stop.\n');
});

client.on('message_create', async (message) => {
    try {
        const chat = await message.getChat();
        const chatName = (chat.name || '').toLowerCase();
        
        // Filter by target group keyword (e.g. "placement", "internship", "cdc")
        // If TARGET_GROUP_KEYWORD is empty or set to '*', listen to all
        const isTargetGroup = TARGET_GROUP_KEYWORD === '*' || 
                              chatName.includes(TARGET_GROUP_KEYWORD) ||
                              (message.body && /placement|internship|campus drive|stipend|ctc|lpa|hiring/i.test(message.body));

        if (!isTargetGroup) {
            return;
        }

        console.log(`\n[Bridge] 📩 Placement message detected from: "${chat.name}"`);
        const sender = message.author || message.from;
        const text = message.body || '';

        let savedFilePath = null;
        let originalFileName = null;
        let fileBuffer = null;
        let mimeType = null;

        // Check if there is an attachment (PDF, image, doc)
        if (message.hasMedia) {
            console.log('[Bridge] 📎 Message contains media attachment. Downloading...');
            const media = await message.downloadMedia();
            if (media) {
                const ext = (media.mimetype.split('/')[1] || 'bin').split(';')[0];
                originalFileName = media.filename || `placement_attachment_${Date.now()}.${ext}`;
                savedFilePath = path.join(UPLOADS_DIR, `${Date.now()}_${originalFileName}`);
                fileBuffer = Buffer.from(media.data, 'base64');
                fs.writeFileSync(savedFilePath, fileBuffer);
                mimeType = media.mimetype;
                console.log(`[Bridge] 💾 Attachment saved: ${savedFilePath}`);
            }
        }

        // Forward to FastAPI Webhook using native fetch (Node 18+)
        console.log('[Bridge] 📡 Forwarding to Placement Tracker API...');
        const formData = new FormData();
        if (text) formData.append('text', text);
        formData.append('sender', chat.name || sender || 'WhatsApp Group');

        if (fileBuffer) {
            const blob = new Blob([fileBuffer], { type: mimeType || 'application/octet-stream' });
            formData.append('file', blob, originalFileName || 'attachment.pdf');
        }

        const res = await fetch(WEBHOOK_URL, {
            method: 'POST',
            body: formData
        });

        const result = await res.json();
        console.log('[Bridge] ✅ API Response:', JSON.stringify(result));

    } catch (err) {
        console.error('[Bridge] ⚠️ Error processing message:', err.message);
    }
});

client.initialize();
