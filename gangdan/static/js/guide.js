/* GangDan - Guided Learning Module */
(function() {
    'use strict';
    var P = 'g-';
    var _inited = false;
    var currentSessionId = null;
    var currentIndex = 0;
    var totalPoints = 0;

    function el(id) { return document.getElementById(P + id); }

    function init() {
        if (_inited) return;
        _inited = true;
        loadSessions();
    }

    async function createSession() {
        if (window._learningSelectedKbs.size === 0) {
            setStatus(getT('no_kb_selected'));
            return;
        }
        el('createBtn').disabled = true;
        setStatus(getT('creating_session') || 'Analyzing knowledge base...');

        try {
            var res = await fetch('/api/learning/guide/create', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    kb_names: Array.from(window._learningSelectedKbs),
                    web_search: el('webSearchToggle') ? el('webSearchToggle').checked : false,
                }),
            });
            var data = await res.json();
            if (data.error) {
                setStatus(data.error);
                return;
            }
            currentSessionId = data.session_id;
            totalPoints = data.knowledge_points.length;
            currentIndex = 0;
            showLearningPanel(data.knowledge_points);
            setStatus('');
            loadSessions();
        } catch (e) {
            setStatus('Error: ' + e.message);
        } finally {
            el('createBtn').disabled = false;
        }
    }

    function showLearningPanel(kps) {
        el('setupPanel').style.display = 'none';
        el('learningPanel').style.display = 'block';
        el('emptyState').style.display = 'none';

        var list = el('kpList');
        list.innerHTML = kps.map(function(kp, i) {
            return '<li class="kp-item ' + (i === 0 ? 'active' : '') + '" id="' + P + 'kp-' + i + '" onclick="GuideModule.selectKp(' + i + ')">' +
                '<div class="kp-title">' + kp.title + '</div>' +
                '<div class="kp-desc">' + kp.description + '</div>' +
            '</li>';
        }).join('');

        updateProgress();
        el('startBtn').style.display = 'block';
        el('nextBtn').style.display = 'none';
        el('summaryBtn').style.display = 'none';
        el('chatSection').style.display = 'none';
    }

    function selectKp(idx) {
        el('kpList').querySelectorAll('.kp-item').forEach(function(item, i) {
            item.classList.toggle('active', i === idx);
        });
    }

    async function startLearning() {
        el('startBtn').style.display = 'none';
        el('nextBtn').style.display = 'block';
        el('chatSection').style.display = 'block';
        await loadLesson();
    }

    async function loadLesson() {
        var content = el('lessonContent');
        content.innerHTML = '<div class="status-msg"><span class="learning-loading"></span> Loading lesson...</div>';
        setStatus('');

        try {
            var res = await fetch('/api/learning/guide/start/' + currentSessionId, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({web_search: el('webSearchToggle') ? el('webSearchToggle').checked : false}),
            });
            var fullText = '';
            content.innerHTML = '';

            await createSSEReader(res, {
                content: function(event) {
                    if (event.content) {
                        fullText += event.content;
                        content.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(fullText) : fullText;
                    }
                    if (event.done && typeof renderMathInElement === 'function') {
                        renderMathInElement(content, {delimiters: [
                            {left: '$$', right: '$$', display: true},
                            {left: '$', right: '$', display: false},
                        ]});
                    }
                },
            }, function(errMsg) { setStatus(errMsg); });
        } catch (e) {
            content.innerHTML = '<div class="status-msg">Error loading lesson</div>';
        }
    }

    async function nextPoint() {
        try {
            var res = await fetch('/api/learning/guide/next/' + currentSessionId, {method: 'POST'});
            var data = await res.json();
            if (data.error) {
                setStatus(data.error);
                return;
            }
            if (data.is_complete) {
                setStatus(getT('learning_complete') || 'Learning Complete!');
                el('nextBtn').style.display = 'none';
                el('summaryBtn').style.display = 'block';
                el('kpList').querySelectorAll('.kp-item').forEach(function(item) {
                    item.classList.add('completed');
                });
                updateProgress(100);
                return;
            }
            currentIndex = data.current_index;
            updateProgress(data.progress_pct);

            el('kpList').querySelectorAll('.kp-item').forEach(function(item, i) {
                item.classList.remove('active');
                if (i < currentIndex) item.classList.add('completed');
                if (i === currentIndex) item.classList.add('active');
            });

            el('chatMessages').innerHTML = '';
            await loadLesson();
        } catch (e) {
            setStatus('Error: ' + e.message);
        }
    }

    async function sendChatMessage() {
        var input = el('chatInput');
        var msg = input.value.trim();
        if (!msg) return;
        input.value = '';

        var messages = el('chatMessages');
        messages.innerHTML += '<div class="guide-chat-msg user">' + msg + '</div>';

        var assistantDiv = document.createElement('div');
        assistantDiv.className = 'guide-chat-msg assistant';
        assistantDiv.innerHTML = '<span class="learning-loading"></span>';
        messages.appendChild(assistantDiv);
        messages.scrollTop = messages.scrollHeight;

        try {
            var res = await fetch('/api/learning/guide/chat/' + currentSessionId, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    message: msg,
                    web_search: el('webSearchToggle') ? el('webSearchToggle').checked : false,
                }),
            });
            var fullText = '';

            await createSSEReader(res, {
                content: function(event) {
                    if (event.content) {
                        fullText += event.content;
                        assistantDiv.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(fullText) : fullText;
                    }
                },
            }, function(errMsg) { assistantDiv.innerHTML = errMsg; });
            messages.scrollTop = messages.scrollHeight;
        } catch (e) {
            assistantDiv.innerHTML = 'Error: ' + e.message;
        }
    }

    async function generateSummary() {
        var content = el('lessonContent');
        content.innerHTML = '<div class="status-msg"><span class="learning-loading"></span> Generating summary...</div>';

        try {
            var res = await fetch('/api/learning/guide/summary/' + currentSessionId);
            var fullText = '';
            content.innerHTML = '';

            await createSSEReader(res, {
                content: function(event) {
                    if (event.content) {
                        fullText += event.content;
                        content.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(fullText) : fullText;
                    }
                    if (event.done && typeof renderMathInElement === 'function') {
                        renderMathInElement(content, {delimiters: [
                            {left: '$$', right: '$$', display: true},
                            {left: '$', right: '$', display: false},
                        ]});
                    }
                },
            }, function(errMsg) { setStatus(errMsg); });
        } catch (e) {
            content.innerHTML = '<div class="status-msg">Error generating summary</div>';
        }
    }

    async function resumeSession(sessionId) {
        try {
            var res = await fetch('/api/learning/guide/session/' + sessionId);
            var data = await res.json();
            if (data.error) { setStatus(data.error); return; }

            currentSessionId = data.session_id;
            totalPoints = data.total_points;
            currentIndex = data.current_index;
            showLearningPanel(data.knowledge_points);
            updateProgress(data.progress_pct);

            el('kpList').querySelectorAll('.kp-item').forEach(function(item, i) {
                item.classList.remove('active');
                if (i < currentIndex) item.classList.add('completed');
                if (i === currentIndex) item.classList.add('active');
            });

            if (data.status === 'completed') {
                el('startBtn').style.display = 'none';
                el('nextBtn').style.display = 'none';
                el('summaryBtn').style.display = 'block';
            } else if (data.status === 'learning') {
                el('startBtn').style.display = 'none';
                el('nextBtn').style.display = 'block';
                el('chatSection').style.display = 'block';
                await loadLesson();
            }
        } catch (e) {
            setStatus('Error: ' + e.message);
        }
    }

    async function loadSessions() {
        try {
            var res = await fetch('/api/learning/guide/sessions');
            var data = await res.json();
            var container = el('sessionList');
            if (!data.sessions || data.sessions.length === 0) {
                container.innerHTML = '<div class="empty-state" style="padding:10px;">No sessions</div>';
                return;
            }
            container.innerHTML = data.sessions.map(function(s) {
                return '<div class="history-item" onclick="GuideModule.resumeSession(\'' + s.session_id + '\')">' +
                    '<div>' +
                        '<div class="hi-title">' + s.kb_names.join(', ') + '</div>' +
                        '<div class="hi-meta">' + s.current_index + '/' + s.total_points + ' points &middot; ' + s.status + ' &middot; ' + s.created_at.split('T')[0] + '</div>' +
                    '</div>' +
                '</div>';
            }).join('');
        } catch (e) {}
    }

    function backToSetup() {
        el('setupPanel').style.display = 'block';
        el('learningPanel').style.display = 'none';
        el('lessonContent').innerHTML = '';
        el('emptyState').style.display = 'block';
        currentSessionId = null;
        setStatus('');
    }

    function updateProgress(pct) {
        if (pct === undefined) pct = totalPoints > 0 ? Math.round((currentIndex / totalPoints) * 100) : 0;
        el('progressFill').style.width = pct + '%';
        el('progressText').textContent = pct + '%';
    }

    function setStatus(msg) {
        setStatusCommon(msg, P + 'statusMsg');
    }

    window.GuideModule = {
        init: init,
        createSession: createSession,
        selectKp: selectKp,
        startLearning: startLearning,
        nextPoint: nextPoint,
        sendChatMessage: sendChatMessage,
        generateSummary: generateSummary,
        resumeSession: resumeSession,
        backToSetup: backToSetup,
    };
})();
