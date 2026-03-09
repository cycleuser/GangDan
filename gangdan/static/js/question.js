/* GangDan - Question Generator Module */
(function() {
    'use strict';
    var P = 'q-';
    var _inited = false;
    var isGeneratingQuestions = false;

    function el(id) { return document.getElementById(P + id); }

    function init() {
        if (_inited) return;
        _inited = true;
        loadHistory();
    }

    async function generateQuestions() {
        if (isGeneratingQuestions) return;
        var topic = el('topicInput').value.trim();
        if (!topic) return;
        if (window._learningSelectedKbs.size === 0) {
            setStatus(getT('no_kb_selected') || 'Please select a knowledge base');
            return;
        }

        isGeneratingQuestions = true;
        el('generateBtn').disabled = true;
        el('questionsContainer').innerHTML = '';
        el('emptyState').style.display = 'none';
        setStatus(getT('generating_questions') || 'Generating questions...');

        var qCount = 0;
        try {
            var res = await fetch('/api/learning/questions/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    kb_names: Array.from(window._learningSelectedKbs),
                    topic: topic,
                    num_questions: parseInt(el('countSlider').value),
                    question_type: el('typeSelect').value,
                    difficulty: el('difficultySelect').value,
                    web_search: el('webSearchToggle') ? el('webSearchToggle').checked : false,
                })
            });

            await createSSEReader(res, {
                status: function(event) { setStatus(event.message); },
                question: function(event) {
                    qCount++;
                    appendQuestion(event.data, qCount);
                },
                done: function(event) {
                    setStatus('Complete: ' + event.count + ' questions generated');
                    loadHistory();
                },
            }, function(errMsg) { setStatus(errMsg); });
        } catch (e) {
            setStatus('Error: ' + e.message);
        } finally {
            isGeneratingQuestions = false;
            el('generateBtn').disabled = false;
        }
    }

    function appendQuestion(q, num) {
        var container = el('questionsContainer');
        var typeLabels = {choice: 'MCQ', written: 'Short Answer', fill_blank: 'Fill Blank', true_false: 'T/F'};

        var optionsHtml = '';
        if (q.options && Object.keys(q.options).length > 0) {
            optionsHtml = '<div class="question-options">' +
                Object.entries(q.options).map(function(entry) {
                    return '<div class="question-option" data-key="' + entry[0] + '">' + entry[0] + '. ' + entry[1] + '</div>';
                }).join('') + '</div>';
        }

        var card = document.createElement('div');
        card.className = 'question-card';
        card.innerHTML =
            '<div class="question-card-header">' +
                '<span class="q-num">Q' + num + '</span>' +
                '<span class="q-type">' + (typeLabels[q.question_type] || q.question_type) + ' &middot; ' + (q.knowledge_point || '') + '</span>' +
            '</div>' +
            '<div class="question-text">' + q.question_text + '</div>' +
            optionsHtml +
            '<button class="btn-learning btn-learning-secondary" style="width:auto; margin-top:8px; padding:5px 14px; font-size:0.82em;" ' +
                'onclick="QuestionModule.toggleAnswer(this)">' + (getT('show_answer') || 'Show Answer') + '</button>' +
            '<div class="question-answer" id="' + P + 'ans-' + q.question_id + '">' +
                '<h4>' + (getT('show_answer') || 'Answer') + ': ' + q.correct_answer + '</h4>' +
                '<p>' + q.explanation + '</p>' +
            '</div>';
        container.appendChild(card);

        if (typeof renderMathInElement === 'function') {
            renderMathInElement(card, {delimiters: [
                {left: '$$', right: '$$', display: true},
                {left: '$', right: '$', display: false},
            ]});
        }
    }

    function toggleAnswer(btn) {
        var ansDiv = btn.nextElementSibling;
        var visible = ansDiv.classList.toggle('visible');
        btn.textContent = visible ? (getT('hide_answer') || 'Hide Answer') : (getT('show_answer') || 'Show Answer');

        if (visible) {
            var card = btn.closest('.question-card');
            var h4Text = ansDiv.querySelector('h4').textContent;
            var correctKey = h4Text.split(': ')[1] ? h4Text.split(': ')[1].trim() : '';
            card.querySelectorAll('.question-option').forEach(function(opt) {
                if (opt.dataset.key === correctKey) opt.classList.add('correct');
                else opt.classList.remove('correct');
            });
        }
    }

    async function loadHistory() {
        try {
            var res = await fetch('/api/learning/questions/list');
            var data = await res.json();
            var container = el('historyList');
            if (!data.batches || data.batches.length === 0) {
                container.innerHTML = '<div class="empty-state" style="padding:10px;">No history</div>';
                return;
            }
            container.innerHTML = data.batches.map(function(b) {
                return '<div class="history-item" onclick="QuestionModule.loadBatch(\'' + b.batch_id + '\')">' +
                    '<div>' +
                        '<div class="hi-title">' + b.topic + '</div>' +
                        '<div class="hi-meta">' + b.count + ' questions &middot; ' + b.difficulty + ' &middot; ' + b.created_at.split('T')[0] + '</div>' +
                    '</div>' +
                    '<button class="hi-delete" onclick="event.stopPropagation(); QuestionModule.deleteBatch(\'' + b.batch_id + '\')">&#215;</button>' +
                '</div>';
            }).join('');
        } catch (e) {}
    }

    async function loadBatch(batchId) {
        try {
            var res = await fetch('/api/learning/questions/' + batchId);
            var data = await res.json();
            el('questionsContainer').innerHTML = '';
            el('emptyState').style.display = 'none';
            setStatus('Loaded: ' + data.topic + ' (' + data.questions.length + ' questions)');
            data.questions.forEach(function(q, i) { appendQuestion(q, i + 1); });
        } catch (e) {}
    }

    async function deleteBatch(batchId) {
        await fetch('/api/learning/questions/' + batchId, {method: 'DELETE'});
        loadHistory();
    }

    function setStatus(msg) {
        setStatusCommon(msg, P + 'statusMsg');
    }

    window.QuestionModule = {
        init: init,
        generateQuestions: generateQuestions,
        toggleAnswer: toggleAnswer,
        loadBatch: loadBatch,
        deleteBatch: deleteBatch,
    };
})();
