'use strict';

const f = [1116352408,1899447441,3049323471,3921009573,961987163,1508970993,2453635748,2870763221,3624381080,310598401,607225278,1426881987,1925078388,2162078206,2614888103,3248222580];
const h = [109,118,109,49]; // "mvm1"
const b = e => ((e*(e+1))&1) == 0;

function w(e) {
    e = e >>> 0;
    e ^= e >>> 16;
    e = Math.imul(e, 2246822507) >>> 0;
    e ^= e >>> 13;
    e = Math.imul(e, 3266489909) >>> 0;
    return (e ^ e >>> 16) >>> 0;
}

function v(e, t) {
    t = t & 31;
    return (e >>> 0, 0 == t) ? e >>> 0 : ((e << t) | (e >>> (32 - t))) >>> 0;
}

function initCustom(seedStr, tmdbId) {
    let t = 2166136261;
    for (let s = 0; s < seedStr.length; s++) {
        t = Math.imul(t ^ seedStr.charCodeAt(s), 16777619) >>> 0;
    }
    let a = w(w(t) ^ w((parseInt(tmdbId, 10) >>> 0) ^ 2654435769)) >>> 0;
    let S = Array(61);
    for (let e = 0; e < 8; e++) {
        if (b(e)) {
            let t = a % 61;
            a = v((a + 2654435769) >>> 0, 7 + (7 & e));
            S[t] = (a ^ w(a)) >>> 0;
            a = w((a + t) >>> 0);
        } else {
            S[e] = f[15 & e];
        }
    }
    return { S, acc: w((2779096485 ^ a) >>> 0) };
}

function generateKeystream(initState, len) {
    const { S, acc: initialAcc } = initState;
    const r = new Uint8Array(len);
    let o = 0;
    let state = { S, acc: initialAcc };
    
    let e_idx = 0;
    while (e_idx < len) {
        let r_S = state.S, acc = state.acc, n = acc % 61;
        let i = 0 - Number(n in r_S);
        let d = r_S[n] >>> 0;
        let s = acc, a = (d ^ Math.imul(2654435769, o + 1)) >>> 0;
        let l = (((s ^ a) >>> 0) | (s & a & i) >>> 0) >>> 0;
        l = (v((l + s) >>> 0, 31 & n) ^ v(s, 31 & Math.imul(n, 7))) >>> 0;
        let newAcc = w((l + 2654435769) >>> 0);
        r_S[n] = newAcc >>> 0;
        state.acc = newAcc >>> 0;
        o++;

        let t = newAcc >>> 0;
        r[e_idx++] = 255 & t;
        if (e_idx < len) r[e_idx++] = (t >>> 8) & 255;
        if (e_idx < len) r[e_idx++] = (t >>> 16) & 255;
        if (e_idx < len) r[e_idx++] = (t >>> 24) & 255;
    }
    return r;
}

function decrypt(encB64, seedStr, tmdbId) {
    try {
        const b64 = encB64.replace(/-/g, '+').replace(/_/g, '/').padEnd(4 * Math.ceil(encB64.length / 4), '=');
        const encBytes = Buffer.from(b64, 'base64');

        const st = initCustom(seedStr, tmdbId);
        const ks = generateKeystream(st, encBytes.length);
        const dec = Buffer.alloc(encBytes.length);
        for (let i = 0; i < encBytes.length; i++) dec[i] = encBytes[i] ^ ks[i];

        if (dec[0] === h[0] && dec[1] === h[1] && dec[2] === h[2] && dec[3] === h[3]) {
            return dec.slice(4).toString('utf8');
        }
    } catch (e) {}
    return '{}';
}

const [,, encB64, seedStr, tmdbId] = process.argv;
if (encB64 && seedStr && tmdbId) {
    console.log(decrypt(encB64, seedStr, tmdbId));
} else {
    console.log('{}');
}
