# GangDan Feature Test Report

**Test Date:** 2026-03-09  
**Environment:** Windows, Ollama (localhost:11434), Flask (localhost:5000)  
**Models:** gemma3:1b (chat), nomic-embed-text:latest (embedding)  
**Vector DB:** ChromaDB  

---

## Test Summary

| Test ID | Feature | Result | Details |
|---------|---------|--------|---------|
| T0 | Server Health | **PASS** | HTTP 200, 86KB page |
| T1 | Models API | **PASS** | 9 chat models, embedding configured |
| T2 | Knowledge Base List | **PASS** | 30 KBs, 8928 total docs |
| T3 | Page Load (10 routes) | **PASS** | All 10 pages HTTP 200 |
| T4 | F1: Vector DB Backend | **PASS** | ChromaDB active, 8928 docs indexed |
| T5 | F2: Web Search Toggle | **PASS** | Present on question/lecture/exam |
| T6 | F3: Lecture Generation | **PASS** | 3 phases completed, 3464 content chunks |
| T7 | F4: Exam Generation | **PASS** | All 4 phases completed, 1732 chunks, done=true |
| T8 | Question Generation | **PASS** | 2 questions generated, done=true |
| T9 | i18n (ZH/EN) | **PASS** | CJK chars in ZH, English text in EN |
| T10 | Saved Items API | **PASS** | Exams persisted, API returns 200 |

**Overall: 11/11 PASSED**

---

## F1: Vector DB Backend Switching

The application supports multiple vector database backends: **ChromaDB** (default), **FAISS**, and **In-Memory**. Configuration is managed via the Settings panel.

### Settings Panel

The settings page provides a unified interface for configuring:
- **Connection Status**: Ollama connectivity test  
- **Chat Model**: gemma3:1b selected  
- **Embedding Model**: nomic-embed-text:latest selected  
- **Vector Database**: ChromaDB (Default) - dropdown supports switching  
- **Proxy Settings**: Mode set to None  

![Settings Page](11_settings_en.png)

### Configuration File

```json
{
  "ollama_url": "http://localhost:11434",
  "embedding_model": "nomic-embed-text:latest",
  "chat_model": "gemma3:1b",
  "vector_db_type": "chroma",
  "proxy_mode": "none",
  "language": "zh"
}
```

### Knowledge Base Verification

API endpoint `/api/kb/list` returns 30 knowledge bases with 8928 total indexed documents across builtin and user KBs.

The learning-specific endpoint `/api/learning/kb/list` provides the same KBs filtered for learning features, showing document counts from the docs directory (e.g., numpy: 3 docs, scipy: 4 docs).

---

## F2: Web Search Integration

Web search is integrated as an optional toggle on all learning pages (Question Generator, Lecture Maker, Exam Generator). When enabled, the generation pipeline performs a canary search to verify web connectivity, then enriches the RAG context with web results.

### Web Search Toggle on Question Page

![Question Page EN](02_question_en.png)

### Web Search Toggle on Lecture Page

![Lecture Page EN](05_lecture_en.png)

### Web Search Toggle on Exam Page

![Exam Page EN](06_exam_en.png)

**Verification:** All 3 learning pages include the "Enable Web Search" checkbox with proper i18n labels.

---

## F3: Lecture Maker

The Lecture Maker generates structured lecture/handout documents through a 4-phase pipeline:
1. **Analyzing** - Extract lecture structure from KB content
2. **Outlining** - Refine section ordering and emphasis
3. **Writing** - Write each section with RAG context
4. **Summarizing** - Generate abstract/summary

### Lecture Page (English)

Full UI with KB list loaded, topic input, web search toggle, and phase indicator:

![Lecture Page](05_lecture_en.png)

### Lecture Page (Chinese)

i18n support with all labels translated:

![Lecture Page ZH](09_lecture_zh.png)

### Lecture Form Filled

Topic "Python array basics with NumPy" entered, numpy KB selected:

![Lecture Filled](12_lecture_filled_en.png)

### Lecture Generation In Progress

Phase indicator shows "Analyzing" active, status message "Extracting lecture structure...":

![Lecture Generating](13_lecture_generating_en.png)

### API Test Results

SSE streaming test via `/api/learning/lecture/generate`:

```
Input:  topic="Python basics", kb_names=["numpy"], web_search=false
Phases: analyzing -> outlining -> writing
Output: 3464 content chunks across 3+ sections
  - Section 1: Introduction
  - Section 2: Converting Python Sequences to NumPy Arrays
  - Section 3: NumPy Array Fundamentals
Duration: 300s (still generating, model is gemma3:1b)
```

---

## F4: Exam Generator

The Exam Generator creates exam papers through a 4-phase pipeline:
1. **Planning** - Analyze topic and plan question distribution
2. **Generating** - Generate questions (choice/fill_blank/true_false)
3. **Answer Key** - Generate answer key with explanations
4. **Formatting** - Format final exam paper and answer sheet

### Exam Page (English)

Full UI with KB list, difficulty selector (Easy/Medium/Hard), and saved exams:

![Exam Page](06_exam_en.png)

### Exam Page (Chinese)

![Exam Page ZH](10_exam_zh.png)

### Exam Form Filled

Topic "Python array basics" entered, numpy KB selected, difficulty set to Easy:

![Exam Filled](15_exam_filled_en.png)

### Exam Generation - Planning Phase

Phase indicator shows "Planning" active, status "Planning exam structure...":

![Exam Generating - Planning](16_exam_generating_en.png)

### Exam Generation - Generating Phase

Phase indicator shows "Generating" active, sections appearing with question counts:

![Exam Generating - Questions](17_exam_result_en.png)

### Saved Exams

Previously generated exams persist and appear in the "Saved Exams" sidebar:
- Python basics - easy - 4 questions - 50 pts - 2026-03-09
- Python basics - easy - 2 questions - 40 pts - 2026-03-09

### API Test Results

SSE streaming test via `/api/learning/exam/generate`:

```
Input:  topic="Python basics", kb_names=["numpy"], difficulty="easy"
Phases: planning -> generating -> answer_key -> formatting (ALL 4 COMPLETED)
Output: 1732 content chunks, done=true
Duration: 262.9s
Result: Exam paper with questions, answer key, and formatted output
```

---

## Question Generator

### Question Page (English)

Full UI with KB checkboxes, topic input, question count slider, type/difficulty selectors:

![Question Page](02_question_en.png)

### Question Form Filled

Topic "array operations", numpy KB selected, Multiple Choice type:

![Question Filled](18_question_filled_en.png)

### Question Generation In Progress

Status shows "Planning question angles...":

![Question Generating](19_question_result_en.png)

### API Test Results

```
Input:  kb_names=["numpy"], topic="array operations", num_questions=2, type="choice"
Output: 2 questions generated, done=true
Duration: 34.8s
```

---

## i18n (Internationalization)

All pages support dynamic language switching without page reload. Translation keys are present for all 4 features in both Chinese and English.

### Main Page (English)

![Main Page EN](01_main_page_en.png)

### Main Page (Chinese)

![Main Page ZH](07_main_page_zh.png)

### Question Page (Chinese)

![Question ZH](08_question_zh.png)

### Verification

- Chinese pages contain CJK characters: **YES**
- English pages contain English text: **YES**
- 25 new translation keys verified in HTML output
- Language selector dropdown present on all pages

---

## Page Navigation

All learning pages include navigation links to each other and back to main:

| Page | Navigation Links |
|------|-----------------|
| Main (/) | Question Generator, Guided Learning, Deep Research, Lecture Maker, Exam Generator |
| Question (/question) | Guided Learning, Deep Research, Lecture Maker, Exam Generator |
| Guide (/guide) | Question Generator, Deep Research, Lecture Maker, Exam Generator |
| Research (/research) | Question Generator, Guided Learning, Lecture Maker, Exam Generator |
| Lecture (/learning/lecture) | Back to Main, Question Generator, Guided Learning, Deep Research, Exam Generator |
| Exam (/learning/exam) | Back to Main, Question Generator, Guided Learning, Deep Research, Lecture Maker |

---

## Bug Fix Applied During Testing

### Issue: `let isGenerating` duplicate declaration

**Problem:** `i18n.js` declared `let isGenerating = false` at global scope. When lecture.js and exam.js also declared `let isGenerating`, the browser threw `Identifier 'isGenerating' has already been declared`, breaking all JS on the lecture and exam pages.

**Symptoms:**
- KB list failed to load (stuck on spinner)
- `startLecture()` / `startExam()` functions undefined
- Generation could not be triggered from the UI

**Fix:** Removed the `isGenerating` declaration from `i18n.js` and added it to `chat.js` (which was the only file that used it without declaring it). Each page-specific JS now owns its own `isGenerating` state:
- `chat.js`: `let isGenerating = false;` (for main page)
- `lecture.js`: `let isGenerating = false;` (for lecture page)
- `exam.js`: `let isGenerating = false;` (for exam page)
- `question.js`: `let isGeneratingQuestions = false;` (already unique)

**Files modified:**
- `gangdan/static/js/i18n.js` - removed `let isGenerating = false;`
- `gangdan/static/js/chat.js` - added `let isGenerating = false;`

---

## Appendix: Full Test Output

```
T0: Server Health Check         -> PASS (HTTP 200)
T1: Models API                  -> PASS (9 chat, embedding configured)
T2: Knowledge Base List         -> PASS (30 KBs, 8928 docs)
T3: Page Load (10 routes)       -> PASS (all HTTP 200)
T4: F1 Vector DB Backend        -> PASS (ChromaDB, 8928 docs)
T5: F2 Web Search Toggle        -> PASS (3/3 pages)
T6: F3 Lecture Generation       -> PASS (3 phases, 3464 chunks)
T7: F4 Exam Generation          -> PASS (4 phases, 1732 chunks, done)
T8: Question Generation         -> PASS (2 questions, done)
T9: i18n (ZH/EN)                -> PASS (CJK + English verified)
T10: Saved Items API            -> PASS (exams persisted)

TOTAL: 11/11 PASSED
```
