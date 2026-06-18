(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.autoCheckCrypto = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  const SHA256_HASH_LENGTH = 32;
  const SHA256_K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];

  function getCrypto() {
    return root.crypto || null;
  }

  function utf8Bytes(value) {
    if (typeof TextEncoder !== "undefined") {
      return new TextEncoder().encode(String(value));
    }
    const bytes = [];
    for (const char of String(value)) {
      const codePoint = char.codePointAt(0);
      if (codePoint <= 0x7f) {
        bytes.push(codePoint);
      } else if (codePoint <= 0x7ff) {
        bytes.push(0xc0 | (codePoint >> 6), 0x80 | (codePoint & 0x3f));
      } else if (codePoint <= 0xffff) {
        bytes.push(0xe0 | (codePoint >> 12), 0x80 | ((codePoint >> 6) & 0x3f), 0x80 | (codePoint & 0x3f));
      } else {
        bytes.push(
          0xf0 | (codePoint >> 18),
          0x80 | ((codePoint >> 12) & 0x3f),
          0x80 | ((codePoint >> 6) & 0x3f),
          0x80 | (codePoint & 0x3f)
        );
      }
    }
    return new Uint8Array(bytes);
  }

  function bytesToHex(bytes) {
    return Array.from(bytes).map((byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  function concatBytes(...items) {
    const total = items.reduce((sum, item) => sum + item.length, 0);
    const result = new Uint8Array(total);
    let offset = 0;
    for (const item of items) {
      result.set(item, offset);
      offset += item.length;
    }
    return result;
  }

  function xorBytes(left, right) {
    const result = new Uint8Array(left.length);
    for (let index = 0; index < left.length; index += 1) {
      result[index] = left[index] ^ right[index];
    }
    return result;
  }

  function rightRotate(value, bits) {
    return (value >>> bits) | (value << (32 - bits));
  }

  function sha256(message) {
    const bytes = message instanceof Uint8Array ? message : new Uint8Array(message);
    const bitLength = bytes.length * 8;
    const paddedLength = (((bytes.length + 9 + 63) >> 6) << 6);
    const padded = new Uint8Array(paddedLength);
    padded.set(bytes);
    padded[bytes.length] = 0x80;
    const high = Math.floor(bitLength / 0x100000000);
    const low = bitLength >>> 0;
    padded[paddedLength - 8] = (high >>> 24) & 0xff;
    padded[paddedLength - 7] = (high >>> 16) & 0xff;
    padded[paddedLength - 6] = (high >>> 8) & 0xff;
    padded[paddedLength - 5] = high & 0xff;
    padded[paddedLength - 4] = (low >>> 24) & 0xff;
    padded[paddedLength - 3] = (low >>> 16) & 0xff;
    padded[paddedLength - 2] = (low >>> 8) & 0xff;
    padded[paddedLength - 1] = low & 0xff;

    let h0 = 0x6a09e667;
    let h1 = 0xbb67ae85;
    let h2 = 0x3c6ef372;
    let h3 = 0xa54ff53a;
    let h4 = 0x510e527f;
    let h5 = 0x9b05688c;
    let h6 = 0x1f83d9ab;
    let h7 = 0x5be0cd19;
    const words = new Uint32Array(64);

    for (let offset = 0; offset < padded.length; offset += 64) {
      for (let index = 0; index < 16; index += 1) {
        const base = offset + (index * 4);
        words[index] = (
          (padded[base] << 24) |
          (padded[base + 1] << 16) |
          (padded[base + 2] << 8) |
          padded[base + 3]
        ) >>> 0;
      }
      for (let index = 16; index < 64; index += 1) {
        const s0 = (rightRotate(words[index - 15], 7) ^ rightRotate(words[index - 15], 18) ^ (words[index - 15] >>> 3)) >>> 0;
        const s1 = (rightRotate(words[index - 2], 17) ^ rightRotate(words[index - 2], 19) ^ (words[index - 2] >>> 10)) >>> 0;
        words[index] = (words[index - 16] + s0 + words[index - 7] + s1) >>> 0;
      }

      let a = h0;
      let b = h1;
      let c = h2;
      let d = h3;
      let e = h4;
      let f = h5;
      let g = h6;
      let h = h7;

      for (let index = 0; index < 64; index += 1) {
        const s1 = (rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25)) >>> 0;
        const ch = ((e & f) ^ ((~e) & g)) >>> 0;
        const temp1 = (h + s1 + ch + SHA256_K[index] + words[index]) >>> 0;
        const s0 = (rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22)) >>> 0;
        const maj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
        const temp2 = (s0 + maj) >>> 0;
        h = g;
        g = f;
        f = e;
        e = (d + temp1) >>> 0;
        d = c;
        c = b;
        b = a;
        a = (temp1 + temp2) >>> 0;
      }

      h0 = (h0 + a) >>> 0;
      h1 = (h1 + b) >>> 0;
      h2 = (h2 + c) >>> 0;
      h3 = (h3 + d) >>> 0;
      h4 = (h4 + e) >>> 0;
      h5 = (h5 + f) >>> 0;
      h6 = (h6 + g) >>> 0;
      h7 = (h7 + h) >>> 0;
    }

    const digest = new Uint8Array(SHA256_HASH_LENGTH);
    [h0, h1, h2, h3, h4, h5, h6, h7].forEach((value, index) => {
      const offset = index * 4;
      digest[offset] = (value >>> 24) & 0xff;
      digest[offset + 1] = (value >>> 16) & 0xff;
      digest[offset + 2] = (value >>> 8) & 0xff;
      digest[offset + 3] = value & 0xff;
    });
    return digest;
  }

  function mgf1(seed, length) {
    const mask = new Uint8Array(length);
    let offset = 0;
    let counter = 0;
    while (offset < length) {
      const counterBytes = new Uint8Array([
        (counter >>> 24) & 0xff,
        (counter >>> 16) & 0xff,
        (counter >>> 8) & 0xff,
        counter & 0xff,
      ]);
      const block = sha256(concatBytes(seed, counterBytes));
      mask.set(block.slice(0, Math.min(block.length, length - offset)), offset);
      offset += block.length;
      counter += 1;
    }
    return mask;
  }

  function base64UrlToBytes(value) {
    const normalized = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    if (typeof atob === "function") {
      const binary = atob(padded);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      return bytes;
    }
    if (typeof Buffer !== "undefined") {
      return new Uint8Array(Buffer.from(padded, "base64"));
    }
    throw new Error("Password encryption requires base64 support.");
  }

  function pemToArrayBuffer(pem) {
    const base64 = String(pem || "").replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s/g, "");
    return base64UrlToBytes(base64).buffer;
  }

  function bytesToBigInt(bytes) {
    let value = 0n;
    for (const byte of bytes) {
      value = (value << 8n) + BigInt(byte);
    }
    return value;
  }

  function bigIntToFixedBytes(value, length) {
    const result = new Uint8Array(length);
    let current = value;
    for (let index = length - 1; index >= 0; index -= 1) {
      result[index] = Number(current & 0xffn);
      current >>= 8n;
    }
    return result;
  }

  function modPow(base, exponent, modulus) {
    let result = 1n;
    let currentBase = base % modulus;
    let currentExponent = exponent;
    while (currentExponent > 0n) {
      if (currentExponent & 1n) result = (result * currentBase) % modulus;
      currentBase = (currentBase * currentBase) % modulus;
      currentExponent >>= 1n;
    }
    return result;
  }

  function randomBytes(length) {
    const cryptoObject = getCrypto();
    if (!cryptoObject || typeof cryptoObject.getRandomValues !== "function") {
      throw new Error("Password encryption requires browser crypto random values.");
    }
    const bytes = new Uint8Array(length);
    cryptoObject.getRandomValues(bytes);
    return bytes;
  }

  async function encryptPasswordWithJwk(password, jwk) {
    if (!jwk || !jwk.n || !jwk.e) {
      throw new Error("Password encryption public key is unavailable.");
    }
    if (typeof BigInt !== "function") {
      throw new Error("Password encryption requires BigInt support.");
    }
    const modulusBytes = base64UrlToBytes(jwk.n);
    const exponentBytes = base64UrlToBytes(jwk.e);
    const keyLength = modulusBytes.length;
    const message = utf8Bytes(password);
    if (message.length > keyLength - (2 * SHA256_HASH_LENGTH) - 2) {
      throw new Error("Password is too long to encrypt.");
    }

    const labelHash = sha256(new Uint8Array(0));
    const paddingLength = keyLength - message.length - (2 * SHA256_HASH_LENGTH) - 2;
    const padding = new Uint8Array(paddingLength);
    const delimiter = new Uint8Array([1]);
    const dataBlock = concatBytes(labelHash, padding, delimiter, message);
    const seed = randomBytes(SHA256_HASH_LENGTH);
    const maskedDataBlock = xorBytes(dataBlock, mgf1(seed, keyLength - SHA256_HASH_LENGTH - 1));
    const maskedSeed = xorBytes(seed, mgf1(maskedDataBlock, SHA256_HASH_LENGTH));
    const encodedMessage = concatBytes(new Uint8Array([0]), maskedSeed, maskedDataBlock);
    const encrypted = modPow(bytesToBigInt(encodedMessage), bytesToBigInt(exponentBytes), bytesToBigInt(modulusBytes));
    return bytesToHex(bigIntToFixedBytes(encrypted, keyLength));
  }

  async function encryptPasswordWithWebCrypto(password, payload) {
    const cryptoObject = getCrypto();
    if (!cryptoObject || !cryptoObject.subtle) {
      throw new Error("WebCrypto is unavailable.");
    }
    const hasJwk = Boolean(payload && payload.public_key_jwk);
    const key = await cryptoObject.subtle.importKey(
      hasJwk ? "jwk" : "spki",
      hasJwk ? payload.public_key_jwk : pemToArrayBuffer(payload.public_key_pem),
      { name: "RSA-OAEP", hash: "SHA-256" },
      false,
      ["encrypt"]
    );
    const encrypted = await cryptoObject.subtle.encrypt(
      { name: "RSA-OAEP" },
      key,
      utf8Bytes(password)
    );
    return bytesToHex(new Uint8Array(encrypted));
  }

  async function encryptPasswordForTransport(password, loadKey) {
    const payload = typeof loadKey === "function" ? await loadKey() : loadKey;
    if (!payload) {
      throw new Error("Password encryption public key is unavailable.");
    }
    const cryptoObject = getCrypto();
    if (cryptoObject && cryptoObject.subtle) {
      return encryptPasswordWithWebCrypto(password, payload);
    }
    return encryptPasswordWithJwk(password, payload.public_key_jwk);
  }

  return {
    encryptPasswordForTransport,
    encryptPasswordWithJwk,
  };
});
