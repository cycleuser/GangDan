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
