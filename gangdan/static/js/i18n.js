// ============================================
// i18n & State Management
// ============================================

// State
let currentLang = window.SERVER_CONFIG.lang;
let isGenerating = false;

// Full translations dictionary for dynamic language switching
const ALL_TRANSLATIONS = window.SERVER_CONFIG.translations;

// Helper: get translation for a key in current language
function getT(key) {
    if (ALL_TRANSLATIONS[key]) {
        return ALL_TRANSLATIONS[key][currentLang] || ALL_TRANSLATIONS[key]['en'] || key;
    }
    return key;
}

// Dynamic T object - updated when language changes
const T = {};
function updateT() {
    for (const key in ALL_TRANSLATIONS) {
        T[key] = ALL_TRANSLATIONS[key][currentLang] || ALL_TRANSLATIONS[key]['en'] || key;
    }
}
updateT(); // Initialize T with current language

// Update all UI text dynamically (does NOT touch conversation content)
// Pre-cache selectors for performance
let _i18nEls = null;
let _i18nPhEls = null;
function updateAllUIText() {
    // Cache element lists on first call (or after DOM changes)
    if (!_i18nEls) _i18nEls = document.querySelectorAll('[data-i18n]');
    if (!_i18nPhEls) _i18nPhEls = document.querySelectorAll('[data-i18n-placeholder]');
    
    requestAnimationFrame(() => {
        _i18nEls.forEach(el => {
            const key = el.getAttribute('data-i18n');
            const val = getT(key);
            if (el.tagName === 'OPTION' && el.value === '') {
                el.textContent = '-- ' + val + ' --';
            } else {
                el.textContent = val;
            }
        });
        _i18nPhEls.forEach(el => {
            el.placeholder = getT(el.getAttribute('data-i18n-placeholder'));
        });
        document.title = getT('app_title');
    });
}

// Language change - AJAX, no page reload, preserves conversations
async function changeLanguage(lang) {
    currentLang = lang;
    updateT();
    updateAllUIText();
    // Persist to backend asynchronously
    fetch('/api/set-language', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: lang })
    });
}
