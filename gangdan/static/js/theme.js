// ============================================
// Theme Manager - Dark/Light Mode Switching
// ============================================

const ThemeManager = (function() {
    'use strict';
    
    // Constants
    const STORAGE_KEY = 'gangdan-theme';
    const THEMES = {
        DARK: 'dark',
        LIGHT: 'light'
    };
    
    // State
    let currentTheme = THEMES.DARK;
    
    /**
     * Initialize theme on page load
     */
    function init() {
        // Check for saved theme preference or default to dark
        const savedTheme = localStorage.getItem(STORAGE_KEY);
        
        if (savedTheme && (savedTheme === THEMES.DARK || savedTheme === THEMES.LIGHT)) {
            currentTheme = savedTheme;
        } else {
            // Check system preference
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
                currentTheme = THEMES.LIGHT;
            }
        }
        
        // Apply theme immediately to prevent flash
        applyTheme(currentTheme, false);
        
        // Listen for system theme changes
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', function(e) {
                // Only auto-switch if user hasn't manually set a preference
                if (!localStorage.getItem(STORAGE_KEY)) {
                    const newTheme = e.matches ? THEMES.LIGHT : THEMES.DARK;
                    applyTheme(newTheme, true);
                }
            });
        }
    }
    
    /**
     * Apply theme to document
     * @param {string} theme - Theme name ('dark' or 'light')
     * @param {boolean} save - Whether to save to localStorage
     */
    function applyTheme(theme, save = true) {
        currentTheme = theme;
        document.documentElement.setAttribute('data-theme', theme);
        
        // Update toggle button UI
        updateToggleButton();
        
        // Save preference
        if (save) {
            localStorage.setItem(STORAGE_KEY, theme);
        }
        
        // Dispatch custom event for other components
        window.dispatchEvent(new CustomEvent('themechange', { 
            detail: { theme: theme }
        }));
    }
    
    /**
     * Toggle between dark and light themes
     */
    function toggle() {
        const newTheme = currentTheme === THEMES.DARK ? THEMES.LIGHT : THEMES.DARK;
        applyTheme(newTheme, true);
        
        // Show toast notification
        const themeName = newTheme === THEMES.DARK ? 
            (T['dark_theme'] || 'Dark Mode') : 
            (T['light_theme'] || 'Light Mode');
        showToast(`${themeName} enabled`, 'info');
    }
    
    /**
     * Set specific theme
     * @param {string} theme - Theme name ('dark' or 'light')
     */
    function setTheme(theme) {
        if (theme === THEMES.DARK || theme === THEMES.LIGHT) {
            applyTheme(theme, true);
        }
    }
    
    /**
     * Get current theme
     * @returns {string} Current theme name
     */
    function getTheme() {
        return currentTheme;
    }
    
    /**
     * Update toggle button visual state
     */
    function updateToggleButton() {
        const toggle = document.getElementById('themeToggle');
        if (!toggle) return;
        
        if (currentTheme === THEMES.DARK) {
            toggle.classList.add('theme-dark');
            toggle.classList.remove('theme-light');
            toggle.title = T['switch_to_light'] || 'Switch to Light Mode';
        } else {
            toggle.classList.add('theme-light');
            toggle.classList.remove('theme-dark');
            toggle.title = T['switch_to_dark'] || 'Switch to Dark Mode';
        }
    }
    
    /**
     * Check if current theme is dark
     * @returns {boolean}
     */
    function isDark() {
        return currentTheme === THEMES.DARK;
    }
    
    /**
     * Check if current theme is light
     * @returns {boolean}
     */
    function isLight() {
        return currentTheme === THEMES.LIGHT;
    }
    
    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
    // Public API
    return {
        toggle: toggle,
        setTheme: setTheme,
        getTheme: getTheme,
        isDark: isDark,
        isLight: isLight,
        THEMES: THEMES
    };
})();
