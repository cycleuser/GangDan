/* GangDan - Exam Paper Generator Module */
(function() {
    'use strict';
    var P = 'e-';
    var _inited = false;
    var isGenerating = false;
    var currentPaperMarkdown = '';
    var currentAnswerKeyMarkdown = '';
    var currentTab = 'paper';

    function el(id) { return document.getElementById(P + id); }

    function init() {
        if (_inited) return;
        _inited = true;
        loadExams();
        el('examActions').style.display = 'none';
    }

    async function startExam() {
        if (isGenerating) return;
        var topic = el('topicInput').value.trim();
        if (!topic) return;
        if (window._learningSelectedKbs.size === 0) {
            setStatus(getT('no_kb_selected') || 'Please select a knowledge base');
            return;
        }

        isGenerating = true;
        currentPaperMarkdown = '';
        currentAnswerKeyMarkdown = '';
        currentTab = 'paper';
        el('startBtn').disabled = true;
        el('paperContent').innerHTML = '';
        el('answerKeyContent').innerHTML = '';
        el('emptyState').style.display = 'none';
        el('phaseSection').style.display = 'block';
        el('sectionList').innerHTML = '';
        el('examActions').style.display = 'none';
        el('examTabs').style.display = 'none';
        switchTab('paper');
        setPhase('planning');
        setStatus(getT('generate_exam') || 'Generating exam...');

        try {
            var res = await fetch('/api/learning/exam/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    topic: topic,
                    kb_names: Array.from(window._learningSelectedKbs),
                    difficulty: el('difficultySelect').value,
                    web_search: el('webSearchToggle') ? el('webSearchToggle').checked : false,
                })
            });

            await createSSEReader(res, {
                phase: function(event) { setPhase(event.phase); setStatus(event.message); },
                status: function(event) { setStatus(event.message); },
                plan: function(event) { updatePlan(event.data); },
                section: function(event) { updateSection(event.data); },
                content: function(event) {
                    if (event.section === 'answer_key') {
                        if (event.content) {
                            currentAnswerKeyMarkdown += event.content;
                            var akEl = el('answerKeyContent');
                            akEl.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(currentAnswerKeyMarkdown) : currentAnswerKeyMarkdown;
                        }
                        if (event.done) {
                            renderMathEl('answerKeyContent');
                        }
                    } else {
                        if (event.content) {
                            currentPaperMarkdown += event.content;
                            var pcEl = el('paperContent');
                            pcEl.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(currentPaperMarkdown) : currentPaperMarkdown;
                        }
                        if (event.done) {
                            renderMathEl('paperContent');
                            el('examTabs').style.display = 'flex';
                            el('examActions').style.display = 'flex';
                        }
                    }
                },
                done: function(event) {
                    setStatus(getT('exam_complete') || 'Exam Complete');
                    setPhase('done');
                    el('examTabs').style.display = 'flex';
                    el('examActions').style.display = 'flex';
                    loadExams();
                },
            }, function(errMsg) { setStatus(errMsg); });
        } catch (e) {
            setStatus('Error: ' + e.message);
        } finally {
            isGenerating = false;
            el('startBtn').disabled = false;
        }
    }

    function renderMathEl(elementId) {
        var mathEl = el(elementId);
        if (mathEl && typeof renderMathInElement === 'function') {
            renderMathInElement(mathEl, {delimiters: [
                {left: '$$', right: '$$', display: true},
                {left: '$', right: '$', display: false},
            ]});
        }
    }

    function setPhase(phase) {
        var phases = ['planning', 'generating', 'answer_key', 'formatting'];
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

    function updatePlan(data) {
        var container = el('sectionList');
        if (!data || !data.sections) return;
        container.innerHTML = data.sections.map(function(s, i) {
            return '<div class="subtopic-card pending" id="' + P + 'sec-' + i + '">' +
                '<div class="subtopic-title">' + (s.title || s.type || '') + '</div>' +
                '<div class="subtopic-overview">' + (s.count || 0) + ' questions &middot; ' + ((s.count || 0) * (s.points_each || 0)) + ' pts</div>' +
            '</div>';
        }).join('');
        if (data.total_points || data.duration_minutes) {
            var meta = document.createElement('div');
            meta.style.cssText = 'font-size:0.8em; color:var(--text-muted); margin-top:8px;';
            meta.textContent = 'Total: ' + (data.total_points || '?') + ' pts \u00B7 ' + (data.duration_minutes || '?') + ' min';
            container.appendChild(meta);
        }
    }

    function updateSection(data) {
        var cards = el('sectionList').querySelectorAll('.subtopic-card');
        cards.forEach(function(card) {
            var titleEl = card.querySelector('.subtopic-title');
            if (titleEl && titleEl.textContent.indexOf(data.title) >= 0) {
                card.className = 'subtopic-card completed';
                var overviewEl = card.querySelector('.subtopic-overview');
                if (overviewEl) {
                    overviewEl.textContent = data.question_count + ' questions \u00B7 ' + data.total_points + ' pts';
                }
            }
        });
    }

    function switchTab(tab) {
        currentTab = tab;
        var paperEl = el('paperContent');
        var answerEl = el('answerKeyContent');
        var tabPaper = el('tabPaper');
        var tabAnswer = el('tabAnswerKey');

        if (tab === 'paper') {
            paperEl.style.display = '';
            answerEl.style.display = 'none';
            tabPaper.classList.add('active');
            tabAnswer.classList.remove('active');
        } else {
            paperEl.style.display = 'none';
            answerEl.style.display = '';
            tabPaper.classList.remove('active');
            tabAnswer.classList.add('active');
        }
    }

    function exportPaper() {
        exportMarkdown(currentPaperMarkdown, 'exam_paper.md');
    }

    function exportAnswerKey() {
        exportMarkdown(currentAnswerKeyMarkdown, 'answer_key.md');
    }

    function copyExam() {
        var content = currentTab === 'answer_key' ? currentAnswerKeyMarkdown : currentPaperMarkdown;
        copyToClipboard(content, function(msg) {
            setStatus(msg);
            setTimeout(function() { setStatus(''); }, 2000);
        });
    }

    async function loadExams() {
        try {
            var res = await fetch('/api/learning/exam/list');
            var data = await res.json();
            var container = el('examList');
            if (!data.exams || data.exams.length === 0) {
                container.innerHTML = '<div class="empty-state" style="padding:10px;">No exams</div>';
                return;
            }
            container.innerHTML = data.exams.map(function(e) {
                return '<div class="history-item" onclick="ExamModule.loadExam(\'' + e.paper_id + '\')">' +
                    '<div>' +
                        '<div class="hi-title">' + e.topic + '</div>' +
                        '<div class="hi-meta">' + e.difficulty + ' &middot; ' + e.question_count + ' questions &middot; ' + e.total_points + ' pts &middot; ' + e.created_at.split('T')[0] + '</div>' +
                    '</div>' +
                    '<button class="hi-delete" onclick="event.stopPropagation(); ExamModule.deleteExam(\'' + e.paper_id + '\')">&#215;</button>' +
                '</div>';
            }).join('');
        } catch (e) {}
    }

    async function loadExam(paperId) {
        try {
            var res = await fetch('/api/learning/exam/' + paperId);
            var data = await res.json();
            if (data.error) { setStatus(data.error); return; }

            el('emptyState').style.display = 'none';

            currentPaperMarkdown = data.paper_markdown || '';
            currentAnswerKeyMarkdown = data.answer_key_markdown || '';

            var paperEl = el('paperContent');
            paperEl.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(currentPaperMarkdown) : currentPaperMarkdown;
            renderMathEl('paperContent');

            var answerEl = el('answerKeyContent');
            answerEl.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(currentAnswerKeyMarkdown) : currentAnswerKeyMarkdown;
            renderMathEl('answerKeyContent');

            el('examTabs').style.display = 'flex';
            el('examActions').style.display = 'flex';
            switchTab('paper');
            setStatus('Loaded: ' + data.topic);

            el('phaseSection').style.display = 'block';
            setPhase('done');
            var stContainer = el('sectionList');
            stContainer.innerHTML = (data.sections || []).map(function(s) {
                return '<div class="subtopic-card completed">' +
                    '<div class="subtopic-title">' + s.title + '</div>' +
                    '<div class="subtopic-overview">' + ((s.questions || []).length) + ' questions \u00B7 ' + s.total_points + ' pts</div>' +
                '</div>';
            }).join('');
        } catch (e) {
            setStatus('Error: ' + e.message);
        }
    }

    async function deleteExam(paperId) {
        await fetch('/api/learning/exam/' + paperId, {method: 'DELETE'});
        loadExams();
    }

    function setStatus(msg) {
        setStatusCommon(msg, P + 'statusMsg');
    }

    window.ExamModule = {
        init: init,
        startExam: startExam,
        switchTab: switchTab,
        exportPaper: exportPaper,
        exportAnswerKey: exportAnswerKey,
        copyExam: copyExam,
        loadExam: loadExam,
        deleteExam: deleteExam,
    };
})();
