// Read-only observation in this child process. Never log payloads or credentials.
const fs = require('node:fs');
const crypto = require('node:crypto');
const original = JSON.stringify;
const allowed = new Set(['glm-5.3-flash-ioa', 'glm-5.3-ioa']);
let previous = '';
JSON.stringify = function(value, replacer, space) {
  const encoded = original.call(this, value, replacer, space);
  try {
    if (value && allowed.has(value.model) && Array.isArray(value.messages)) {
      const record = {model: value.model, message_count: value.messages.length,
        messages_sha256: crypto.createHash('sha256').update(original(value.messages)).digest('hex')};
      for (const key of ['reasoning_effort', 'enable_thinking', 'max_tokens', 'max_completion_tokens']) {
        const item = value[key];
        if (typeof item === 'number' || typeof item === 'boolean' ||
            ['low', 'minimal', 'medium', 'high', 'max'].includes(item)) record[key] = item;
      }
      for (const [container, key] of [['thinking', 'type'], ['thinking', 'budget_tokens'], ['reasoning', 'effort']]) {
        const item = value[container]?.[key];
        if (typeof item === 'number' || ['enabled', 'disabled', 'low', 'high', 'max'].includes(item))
          record[container + '.' + key] = item;
      }
      const signature = original(record);
      if (signature !== previous && process.env.CWH_GLM_WIRE_OBSERVER_FILE) {
        fs.appendFileSync(process.env.CWH_GLM_WIRE_OBSERVER_FILE, signature + '\n');
        previous = signature;
      }
    }
  } catch (_) { /* Observation cannot alter execution. */ }
  return encoded;
};
