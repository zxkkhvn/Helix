// api.js
const API_BASE = "";

async function api(path, options = {}) {
    const res = await fetch(API_BASE + path, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...options.headers }
    });
    const data = await res.json();
    if (!res.ok) {
        let msg = data.detail;
        if (typeof msg === 'object') msg = JSON.stringify(msg, null, 2);
        throw new Error(msg || JSON.stringify(data));
    }
    return data;
}
