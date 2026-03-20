// ============================================
// UI Utilities
// ============================================

var _learningModules = ['question', 'guide', 'research', 'lecture', 'exam'];
var _learningInited = {};

function showPanel(name, btn) {
    document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
    document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
    document.getElementById('panel-' + name).classList.add('active');
    if (btn) {
        btn.classList.add('active');
    }
    
    // Lazy-init for settings panel
    if (name === 'settings') {
        if (typeof onResearchProviderChange === 'function') onResearchProviderChange();
    }
    
    // Lazy-init for learning modules
    if (_learningModules.indexOf(name) >= 0) {
        if (!_learningInited._kbLoaded) {
            _learningInited._kbLoaded = true;
            // Invalidate i18n cache so new panel elements are picked up
            if (typeof invalidateI18nCache === 'function') invalidateI18nCache();
            if (typeof loadSharedKbList === 'function') loadSharedKbList();
        }
        if (!_learningInited[name]) {
            _learningInited[name] = true;
            var modMap = {
                question: 'QuestionModule', guide: 'GuideModule',
                research: 'ResearchModule', lecture: 'LectureModule', exam: 'ExamModule'
            };
            var mod = window[modMap[name]];
            if (mod && typeof mod.init === 'function') mod.init();
        }
    }
}

// Toast notification
function showToast(message, type) {
    type = type || '';
    var toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast ' + type + ' show';
    setTimeout(function() { toast.classList.remove('show'); }, 3000);
}

// ============================================
// Theme Manager
// ============================================

var ThemeManager = (function() {
    var STORAGE_KEY = 'gangdan-theme';
    var DEFAULT_THEME = 'dark';
    
    function init() {
        var saved = localStorage.getItem(STORAGE_KEY);
        var systemPref = getSystemPreference();
        var theme = saved || systemPref || DEFAULT_THEME;
        apply(theme, false);
        watchSystemPreference();
        
        // Apply theme immediately to prevent flash
        if (document.readyState === 'loading') {
            document.documentElement.setAttribute('data-theme', theme);
        }
    }
    
    function getSystemPreference() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
            return 'light';
        }
        return 'dark';
    }
    
    function apply(theme, save) {
        document.documentElement.setAttribute('data-theme', theme);
        if (save !== false) {
            localStorage.setItem(STORAGE_KEY, theme);
        }
        updateToggleIcon(theme);
        updateColorScheme(theme);
    }
    
    function updateColorScheme(theme) {
        document.documentElement.style.colorScheme = theme;
    }
    
    function updateToggleIcon(theme) {
        var toggle = document.getElementById('themeToggle');
        if (!toggle) return;
        
        var darkIcon = toggle.querySelector('.theme-icon-dark');
        var lightIcon = toggle.querySelector('.theme-icon-light');
        
        if (darkIcon && lightIcon) {
            darkIcon.style.display = theme === 'dark' ? 'inline' : 'none';
            lightIcon.style.display = theme === 'light' ? 'inline' : 'none';
        }
    }
    
    function toggle() {
        var current = document.documentElement.getAttribute('data-theme') || DEFAULT_THEME;
        var newTheme = current === 'dark' ? 'light' : 'dark';
        apply(newTheme, true);
        
        // Show toast notification
        var themeName = newTheme === 'dark' ? (getT('dark_theme') || 'Dark Theme') : (getT('light_theme') || 'Light Theme');
        showToast(themeName, 'success');
    }
    
    function watchSystemPreference() {
        if (!window.matchMedia) return;
        
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
            // Only auto-switch if user hasn't set a preference
            if (!localStorage.getItem(STORAGE_KEY)) {
                apply(e.matches ? 'dark' : 'light', false);
            }
        });
    }
    
    function getCurrentTheme() {
        return document.documentElement.getAttribute('data-theme') || DEFAULT_THEME;
    }
    
    // Initialize immediately to prevent flash of wrong theme
    init();
    
    // Public API
    return {
        init: init,
        toggle: toggle,
        apply: apply,
        getCurrentTheme: getCurrentTheme
    };
})();

// Initialize theme on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    ThemeManager.init();
});