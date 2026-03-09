/* GangDan - Lecture & Handout Maker Module */
(function() {
    'use strict';
    var P = 'l-';
    var _inited = false;
    var isGenerating = false;
    var currentLectureMarkdown = '';

    function el(id) { return document.getElementById(P + id); }

    function init() {
        if (_inited) return;
        _inited = true;
        loadLectures();
        el('lectureActions').style.display = 'none';
    }

    async function startLecture() {
        if (isGenerating) return;
        var topic = el('topicInput').value.trim();
        if (!topic) return;
        if (window._learningSelectedKbs.size === 0) {
            setStatus(getT('no_kb_selected') || 'Please select a knowledge base');
            return;
        }

        isGenerating = true;
        currentLectureMarkdown = '';
        el('startBtn').disabled = true;
        el('lectureContent').innerHTML = '';
        el('emptyState').style.display = 'none';
        el('phaseSection').style.display = 'block';
        el('outlineList').innerHTML = '';
        el('lectureActions').style.display = 'none';
        setPhase('analyzing');
        setStatus(getT('generate_lecture') || 'Generating lecture...');

        try {
            var res = await fetch('/api/learning/lecture/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    topic: topic,
                    kb_names: Array.from(window._learningSelectedKbs),
                    web_search: el('webSearchToggle') ? el('webSearchToggle').checked : false,
                })
            });

            await createSSEReader(res, {
                phase: function(event) { setPhase(event.phase); setStatus(event.message); },
                status: function(event) { setStatus(event.message); },
                outline: function(event) { updateOutline(event.data); },
                section: function(event) { updateSectionStatus(event.index, event.title); },
                content: function(event) {
                    var contentEl = el('lectureContent');
                    if (event.content) {
                        currentLectureMarkdown += event.content;
                        contentEl.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(currentLectureMarkdown) : currentLectureMarkdown;
                    }
                    if (event.done) {
                        if (typeof renderMathInElement === 'function') {
                            renderMathInElement(contentEl, {delimiters: [
                                {left: '$$', right: '$$', display: true},
                                {left: '$', right: '$', display: false},
                            ]});
                        }
                        el('lectureActions').style.display = 'flex';
                    }
                },
                done: function(event) {
                    setStatus(getT('lecture_complete') || 'Lecture Complete');
                    setPhase('done');
                    loadLectures();
                },
            }, function(errMsg) { setStatus(errMsg); });
        } catch (e) {
            setStatus('Error: ' + e.message);
        } finally {
            isGenerating = false;
            el('startBtn').disabled = false;
        }
    }

    function setPhase(phase) {
        var phases = ['analyzing', 'outlining', 'writing', 'summarizing'];
        phases.forEach(function(p) {
            var phEl = el('phase-' + p);
            if (phEl) phEl.classList.remove('active', 'completed');
        });

        var idx = phases.indexOf(phase);
        if (idx >= 0) {
            for (var i = 0; i < idx; i++) {
                var phEl = el('phase-' + phases[i]);
                if (phEl) phEl.classList.add('completed');
            }
            var activeEl = el('phase-' + phase);
            if (activeEl) activeEl.classList.add('active');
        } else if (phase === 'done') {
            phases.forEach(function(p) {
                var phEl = el('phase-' + p);
                if (phEl) phEl.classList.add('completed');
            });
        }
    }

    function updateOutline(data) {
        var container = el('outlineList');
        container.innerHTML = (data || []).map(function(s, i) {
            return '<div class="subtopic-card pending" id="' + P + 'outline-' + i + '">' +
                '<div class="subtopic-title">' + (s.title || '') + '</div>' +
                '<div class="subtopic-overview">' + (s.instruction || s.emphasis || '') + '</div>' +
            '</div>';
        }).join('');
    }

    function updateSectionStatus(index, title) {
        var container = el('outlineList');
        var cards = container.querySelectorAll('.subtopic-card');
        cards.forEach(function(card, i) {
            if (i < index) card.className = 'subtopic-card completed';
            else if (i === index) card.className = 'subtopic-card active';
        });
    }

    function exportLecture() {
        exportMarkdown(currentLectureMarkdown, 'lecture.md');
    }

    function copyLecture() {
        copyToClipboard(currentLectureMarkdown, function(msg) {
            setStatus(msg);
            setTimeout(function() { setStatus(''); }, 2000);
        });
    }

    async function loadLectures() {
        try {
            var res = await fetch('/api/learning/lecture/list');
            var data = await res.json();
            var container = el('lectureList');
            if (!data.lectures || data.lectures.length === 0) {
                container.innerHTML = '<div class="empty-state" style="padding:10px;">No lectures</div>';
                return;
            }
            container.innerHTML = data.lectures.map(function(l) {
                return '<div class="history-item" onclick="LectureModule.loadLecture(\'' + l.lecture_id + '\')">' +
                    '<div>' +
                        '<div class="hi-title">' + l.topic + '</div>' +
                        '<div class="hi-meta">' + l.section_count + ' sections &middot; ' + l.created_at.split('T')[0] + '</div>' +
                    '</div>' +
                    '<button class="hi-delete" onclick="event.stopPropagation(); LectureModule.deleteLecture(\'' + l.lecture_id + '\')">&#215;</button>' +
                '</div>';
            }).join('');
        } catch (e) {}
    }

    async function loadLecture(lectureId) {
        try {
            var res = await fetch('/api/learning/lecture/' + lectureId);
            var data = await res.json();
            if (data.error) { setStatus(data.error); return; }

            el('emptyState').style.display = 'none';
            currentLectureMarkdown = data.lecture_markdown || '';
            var content = el('lectureContent');
            content.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(currentLectureMarkdown) : currentLectureMarkdown;

            if (typeof renderMathInElement === 'function') {
                renderMathInElement(content, {delimiters: [
                    {left: '$$', right: '$$', display: true},
                    {left: '$', right: '$', display: false},
                ]});
            }

            el('lectureActions').style.display = 'flex';
            setStatus('Loaded: ' + data.topic);

            el('phaseSection').style.display = 'block';
            setPhase('done');
            var stContainer = el('outlineList');
            stContainer.innerHTML = (data.sections || []).map(function(s) {
                return '<div class="subtopic-card completed">' +
                    '<div class="subtopic-title">' + s.title + '</div>' +
                '</div>';
            }).join('');
        } catch (e) {
            setStatus('Error: ' + e.message);
        }
    }

    async function deleteLecture(lectureId) {
        await fetch('/api/learning/lecture/' + lectureId, {method: 'DELETE'});
        loadLectures();
    }

    function setStatus(msg) {
        setStatusCommon(msg, P + 'statusMsg');
    }

    window.LectureModule = {
        init: init,
        startLecture: startLecture,
        exportLecture: exportLecture,
        copyLecture: copyLecture,
        loadLecture: loadLecture,
        deleteLecture: deleteLecture,
    };
})();
