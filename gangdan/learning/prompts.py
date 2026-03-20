"""LLM prompt templates for the learning module (bilingual zh/en)."""


def get_prompt(key: str, lang: str = "en") -> str:
    """Get a prompt template by key and language."""
    lang = lang if lang in ("zh", "en") else "en"
    return PROMPTS.get(key, {}).get(lang, PROMPTS.get(key, {}).get("en", ""))


# =============================================================================
# Question Generator Prompts
# =============================================================================

PROMPTS = {
    # Step 1: Plan question focuses from a topic
    "question_plan": {
        "zh": """你是一个教育内容规划师。根据以下知识库内容和用户指定的主题，规划 {num_questions} 个不同角度的考察方向。

主题：{topic}
题型：{question_type}

知识库内容摘要：
{context}

请以 JSON 格式返回，仅输出 JSON，不要有其他文字：
{{"focuses": ["角度1的简短描述", "角度2的简短描述", ...]}}""",
        "en": """You are an educational content planner. Based on the following knowledge base content and topic, plan {num_questions} different question focuses/angles.

Topic: {topic}
Question type: {question_type}

Knowledge base content summary:
{context}

Return ONLY a JSON object, no other text:
{{"focuses": ["brief description of angle 1", "brief description of angle 2", ...]}}"""
    },

    # Step 2: Generate a single question
    "question_generate_choice": {
        "zh": """你是一个出题专家。根据以下知识内容和考察角度，生成一道{difficulty}难度的选择题。

考察角度：{focus}
知识内容：
{context}

请以 JSON 格式返回，仅输出 JSON：
{{
  "question_text": "题目文本",
  "options": {{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}},
  "correct_answer": "正确选项字母，如 A",
  "explanation": "详细解析",
  "knowledge_point": "考察的知识点"
}}""",
        "en": """You are a question generation expert. Based on the following knowledge content and focus angle, generate a {difficulty} difficulty multiple-choice question.

Focus angle: {focus}
Knowledge content:
{context}

Return ONLY a JSON object, no other text:
{{
  "question_text": "question text",
  "options": {{"A": "option A", "B": "option B", "C": "option C", "D": "option D"}},
  "correct_answer": "correct option letter, e.g. A",
  "explanation": "detailed explanation",
  "knowledge_point": "tested knowledge point"
}}"""
    },

    "question_generate_written": {
        "zh": """你是一个出题专家。根据以下知识内容和考察角度，生成一道{difficulty}难度的简答题。

考察角度：{focus}
知识内容：
{context}

请以 JSON 格式返回，仅输出 JSON：
{{
  "question_text": "题目文本",
  "correct_answer": "参考答案",
  "explanation": "详细解析",
  "knowledge_point": "考察的知识点"
}}""",
        "en": """You are a question generation expert. Based on the following knowledge content and focus angle, generate a {difficulty} difficulty short-answer question.

Focus angle: {focus}
Knowledge content:
{context}

Return ONLY a JSON object, no other text:
{{
  "question_text": "question text",
  "correct_answer": "reference answer",
  "explanation": "detailed explanation",
  "knowledge_point": "tested knowledge point"
}}"""
    },

    "question_generate_fill_blank": {
        "zh": """你是一个出题专家。根据以下知识内容和考察角度，生成一道{difficulty}难度的填空题。用 _____ 标记空白处。

考察角度：{focus}
知识内容：
{context}

请以 JSON 格式返回，仅输出 JSON：
{{
  "question_text": "题目文本，用 _____ 表示需要填写的部分",
  "correct_answer": "正确答案",
  "explanation": "详细解析",
  "knowledge_point": "考察的知识点"
}}""",
        "en": """You are a question generation expert. Based on the following knowledge content and focus angle, generate a {difficulty} difficulty fill-in-the-blank question. Use _____ to mark blanks.

Focus angle: {focus}
Knowledge content:
{context}

Return ONLY a JSON object, no other text:
{{
  "question_text": "question text with _____ for blanks",
  "correct_answer": "correct answer",
  "explanation": "detailed explanation",
  "knowledge_point": "tested knowledge point"
}}"""
    },

    "question_generate_true_false": {
        "zh": """你是一个出题专家。根据以下知识内容和考察角度，生成一道{difficulty}难度的判断题。

考察角度：{focus}
知识内容：
{context}

请以 JSON 格式返回，仅输出 JSON：
{{
  "question_text": "判断题的陈述",
  "correct_answer": "正确 或 错误",
  "explanation": "详细解析",
  "knowledge_point": "考察的知识点"
}}""",
        "en": """You are a question generation expert. Based on the following knowledge content and focus angle, generate a {difficulty} difficulty true/false question.

Focus angle: {focus}
Knowledge content:
{context}

Return ONLY a JSON object, no other text:
{{
  "question_text": "a true/false statement",
  "correct_answer": "True or False",
  "explanation": "detailed explanation",
  "knowledge_point": "tested knowledge point"
}}"""
    },

    # =============================================================================
    # Guided Learning Prompts
    # =============================================================================

    "guide_analyze_kb": {
        "zh": """你是一个学习规划师。分析以下知识库文档内容，提取 3-5 个核心知识点，为学习者创建一个循序渐进的学习计划。

知识库文档摘要：
{content}

请以 JSON 格式返回，仅输出 JSON：
{{
  "knowledge_points": [
    {{
      "title": "知识点标题",
      "description": "该知识点的详细说明（50-100字）",
      "key_concepts": ["概念1", "概念2", "概念3"]
    }}
  ]
}}

要求：
- 按从基础到进阶的顺序排列
- 每个知识点应该是独立的学习单元
- 标题简洁明确""",
        "en": """You are a learning planner. Analyze the following knowledge base document content and extract 3-5 core knowledge points to create a progressive learning plan.

Knowledge base document summary:
{content}

Return ONLY a JSON object, no other text:
{{
  "knowledge_points": [
    {{
      "title": "knowledge point title",
      "description": "detailed description of this point (50-100 words)",
      "key_concepts": ["concept 1", "concept 2", "concept 3"]
    }}
  ]
}}

Requirements:
- Order from basic to advanced
- Each point should be an independent learning unit
- Titles should be concise and clear"""
    },

    "guide_generate_lesson": {
        "zh": """你是一个优秀的教师。请为以下知识点生成一份详细的教学内容，使用 Markdown 格式。

知识点：{title}
描述：{description}
核心概念：{concepts}

补充知识库内容：
{context}

要求：
- 使用清晰的标题和层次结构
- 包含概念解释、示例和要点总结
- 如果涉及代码，请提供代码示例
- 使用通俗易懂的语言
- 在适当位置添加重点提示
- 内容应完整且有教学价值""",
        "en": """You are an excellent teacher. Generate detailed lesson content for the following knowledge point in Markdown format.

Knowledge point: {title}
Description: {description}
Key concepts: {concepts}

Supplementary knowledge base content:
{context}

Requirements:
- Use clear headings and hierarchy
- Include concept explanations, examples, and key takeaways
- Provide code examples if relevant
- Use clear and accessible language
- Add important tips where appropriate
- Content should be complete and educational"""
    },

    "guide_chat": {
        "zh": """你是一个耐心的学习辅导老师。学生正在学习以下知识点，请根据上下文回答他的问题。

当前学习的知识点：{title}
知识点描述：{description}

之前的对话：
{chat_history}

请用通俗易懂的语言回答，必要时举例说明。""",
        "en": """You are a patient learning tutor. The student is currently studying the following knowledge point. Answer their question based on context.

Current knowledge point: {title}
Description: {description}

Previous conversation:
{chat_history}

Answer in clear, accessible language. Use examples when helpful."""
    },

    "guide_summary": {
        "zh": """你是一个学习总结专家。学生已完成以下知识点的学习，请生成一份学习总结。

学习的知识点：
{points_summary}

学习过程中的问答：
{chat_summary}

请生成一份 Markdown 格式的学习总结，包括：
1. 学习概览
2. 各知识点要点回顾
3. 学习建议和下一步方向""",
        "en": """You are a learning summary expert. The student has completed studying the following knowledge points. Generate a learning summary.

Knowledge points studied:
{points_summary}

Q&A during learning:
{chat_summary}

Generate a Markdown learning summary including:
1. Learning overview
2. Key takeaways for each knowledge point
3. Learning recommendations and next steps"""
    },

    # =============================================================================
    # Deep Research Prompts
    # =============================================================================

    "research_decompose": {
        "zh": """你是一个研究规划专家。将以下研究主题分解为 {num_subtopics} 个子主题，每个子主题应该覆盖该主题的不同方面。

研究主题：{topic}

请以 JSON 格式返回，仅输出 JSON：
{{
  "subtopics": [
    {{
      "title": "子主题标题",
      "overview": "该子主题的简要描述（1-2句话）"
    }}
  ]
}}""",
        "en": """You are a research planning expert. Decompose the following research topic into {num_subtopics} subtopics, each covering a different aspect.

Research topic: {topic}

Return ONLY a JSON object, no other text:
{{
  "subtopics": [
    {{
      "title": "subtopic title",
      "overview": "brief description of this subtopic (1-2 sentences)"
    }}
  ]
}}"""
    },

    "research_summarize": {
        "zh": """你是一个严谨的学术研究助手。你必须严格基于以下检索到的知识库内容撰写研究笔记。

子主题：{subtopic}
子主题描述：{overview}

检索到的内容（每段内容前标注了来源文件）：
{rag_content}

严格要求：
1. 只使用上述检索内容中的信息，绝对不要编造或添加任何内容中没有的信息
2. 每个事实陈述后必须标注来源，格式为 [来源: 文件名]
3. 如果检索内容不足以回答该子主题，明确说明"检索内容不足"，不要猜测
4. 不要使用"众所周知"、"一般认为"等模糊表述
5. 对于不确定的内容，使用"根据XX文档..."等限定性表述

请撰写研究笔记（200-400字），所有内容必须有明确来源。""",
        "en": """You are a rigorous academic research assistant. You MUST strictly base your notes on the following retrieved content.

Subtopic: {subtopic}
Description: {overview}

Retrieved content (each passage is labeled with its source file):
{rag_content}

Strict requirements:
1. Use ONLY information from the retrieved content above. DO NOT fabricate or add any information not present.
2. Every factual statement must cite its source using [Source: filename] format.
3. If the retrieved content is insufficient for this subtopic, clearly state "insufficient retrieved content" - do not guess.
4. Avoid vague expressions like "it is well known" or "generally considered".
5. For uncertain content, use qualified expressions like "According to XX document..."

Write research notes (200-400 words). All content must have clear sources."""
    },

    "research_outline": {
        "zh": """你是一个研究报告规划专家。根据以下研究主题和各子主题的研究笔记，生成一份报告大纲。

研究主题：{topic}

子主题研究笔记：
{notes_summary}

请以 JSON 格式返回报告大纲，仅输出 JSON：
{{
  "sections": [
    {{
      "title": "章节标题",
      "instruction": "该章节应涵盖的内容要点"
    }}
  ]
}}

要求：
- 第一个章节应为引言/概述
- 最后一个章节应为总结
- 中间章节对应各子主题""",
        "en": """You are a research report planning expert. Based on the following research topic and subtopic notes, generate a report outline.

Research topic: {topic}

Subtopic research notes:
{notes_summary}

Return ONLY a JSON object, no other text:
{{
  "sections": [
    {{
      "title": "section title",
      "instruction": "key points this section should cover"
    }}
  ]
}}

Requirements:
- First section should be an introduction/overview
- Last section should be a conclusion
- Middle sections correspond to subtopics"""
    },

    "research_write_section": {
        "zh": """你是一个严谨的学术报告撰写专家。请严格基于以下研究笔记撰写报告章节。

章节标题：{section_title}
内容要求：{instruction}

相关研究笔记（已标注来源）：
{notes}

严格要求：
1. 所有内容必须来自上述研究笔记，绝对不要编造或添加笔记中没有的信息
2. 每个事实陈述后必须保留原有的来源标注，或使用 [来源: 文件名] 格式
3. 如果研究笔记内容不足，直接说明"该方面资料不足"，不要用模糊语言填充
4. 不要使用"众所周知"、"众所周知"等无来源的表述
5. 对于具体数据、定义、结论，必须有明确的来源引用

请使用 Markdown 格式撰写此章节内容。内容应严谨、有据可查。""",
        "en": """You are a rigorous academic report writing expert. Write a section STRICTLY based on the following research notes.

Section title: {section_title}
Content requirements: {instruction}

Related research notes (with source citations):
{notes}

Strict requirements:
1. All content must come from the research notes above. DO NOT fabricate or add any information not present in the notes.
2. Every factual statement must retain the original source citation or use [Source: filename] format.
3. If research notes are insufficient, clearly state "insufficient material on this aspect" - do not fill with vague language.
4. Avoid unsupported expressions like "it is well known".
5. All specific data, definitions, and conclusions must have clear source citations.

Write this section in Markdown format. Content must be rigorous and verifiable."""
    },

    # =============================================================================
    # RAG Note Compression (Phase 2 - Quality Gates)
    # =============================================================================

    "rag_compress": {
        "zh": """你是一个笔记助手。根据查询"{query}"，从以下内容中提取并总结最相关的事实。

内容（包含来源标注）：
{context}

要求：
1. 只提取内容中存在的信息，不要编造
2. 保留每条信息的来源标注，格式为 [来源: 文件名]
3. 输出简洁的摘要（100-300字），只保留与查询直接相关的信息
4. 如果内容不足以回答查询，说明"内容不足"

请直接输出摘要，保留来源标注。""",
        "en": """You are a note-taking assistant. Given the query "{query}", extract and summarize only the most relevant facts from the following content.

Content (with source labels):
{context}

Requirements:
1. Extract ONLY information present in the content. Do not fabricate.
2. Preserve source labels for each piece of information using [Source: filename] format.
3. Output a concise summary (100-300 words), keeping only information directly relevant to the query.
4. If content is insufficient for the query, state "insufficient content".

Output the summary directly, preserving source citations."""
    },

    # =============================================================================
    # Question Generation V2 Prompts (Phase 4 - Bloom's Taxonomy)
    # =============================================================================

    "question_plan_v2": {
        "zh": """你是一个教育内容规划师。根据以下知识库内容和用户指定的主题，规划 {num_questions} 个不同角度的考察方向。
对于每个角度，指定认知水平：
- remember（记忆：回忆事实）
- understand（理解：解释概念）
- apply（应用：在新情境中使用）
- analyze（分析：分解结构）
- evaluate（评价：判断优劣）
- create（创造：设计新方案）

主题：{topic}
题型：{question_type}
难度偏好：{difficulty}

知识库内容摘要：
{context}

请以 JSON 格式返回，仅输出 JSON：
{{"focuses": [{{"angle": "角度描述", "bloom_level": "认知水平"}}, ...]}}""",
        "en": """You are an educational content planner. Based on the following knowledge base content and topic, plan {num_questions} different question focuses.
For each focus, specify the cognitive level:
- remember (recall facts)
- understand (explain concepts)
- apply (use in new situations)
- analyze (break down structure)
- evaluate (judge quality)
- create (design new solutions)

Topic: {topic}
Question type: {question_type}
Difficulty preference: {difficulty}

Knowledge base content summary:
{context}

Return ONLY a JSON object:
{{"focuses": [{{"angle": "focus description", "bloom_level": "cognitive level"}}, ...]}}"""
    },

    # =============================================================================
    # Deep Research V2 Prompts (Phase 0 - Topic Rephrasing)
    # =============================================================================

    "research_rephrase": {
        "zh": """你是一个研究主题优化专家。请优化以下研究主题，使其更加清晰和具体。

原始主题：{topic}

要求：
- 澄清模糊的术语
- 展开缩写
- 添加必要的上下文
- 保持简洁（不超过一句话）
- 如果原始主题已经足够清晰，直接返回原始主题

请只输出优化后的主题文本，不要有任何其他内容。""",
        "en": """You are a research topic optimization expert. Refine the following research topic to make it clearer and more specific.

Original topic: {topic}

Requirements:
- Clarify ambiguous terms
- Expand abbreviations
- Add necessary context
- Keep it concise (one sentence max)
- If the original topic is already clear, return it as-is

Output ONLY the refined topic text, nothing else."""
    },

    # =============================================================================
    # Deep Research V2 Prompts (Autonomous Loop - Evaluate & Expand)
    # =============================================================================

    "research_evaluate_findings": {
        "zh": """你是一个研究质量评估专家。评估以下研究主题的各子主题研究结果是否充分。

研究主题：{topic}

各子主题研究情况：
{notes_summary}

请判断研究结果是否充分。如果某些子主题内容薄弱（字数过少、来源不足），列出它们。

以 JSON 格式返回，仅输出 JSON：
{{
  "sufficient": true或false,
  "weak_subtopics": ["薄弱子主题的标题1", "薄弱子主题的标题2"],
  "reasoning": "简要说明判断理由"
}}""",
        "en": """You are a research quality evaluator. Assess whether the following research findings are sufficient.

Research topic: {topic}

Subtopic research status:
{notes_summary}

Judge whether the findings are comprehensive. If some subtopics have thin content (too few words, insufficient sources), list them.

Return ONLY a JSON object:
{{
  "sufficient": true or false,
  "weak_subtopics": ["title of weak subtopic 1", "title of weak subtopic 2"],
  "reasoning": "brief explanation of your assessment"
}}"""
    },

    "research_expand_queries": {
        "zh": """你是一个研究扩展专家。以下子主题的研究结果不够充分，请生成后续查询来深化研究。

研究主题：{topic}

薄弱子主题：
{weak_subtopics}

请为每个薄弱子主题生成一个更具体的后续查询，并可选地建议1-2个新的子主题来填补研究空白。

以 JSON 格式返回，仅输出 JSON：
{{
  "follow_up_queries": [
    {{"subtopic": "子主题标题", "query": "更具体的查询"}}
  ],
  "new_subtopics": [
    {{"title": "新子主题标题", "overview": "简要描述"}}
  ]
}}""",
        "en": """You are a research expansion expert. The following subtopics have insufficient findings. Generate follow-up queries to deepen the research.

Research topic: {topic}

Weak subtopics:
{weak_subtopics}

Generate a more specific follow-up query for each weak subtopic, and optionally suggest 1-2 new subtopics to fill research gaps.

Return ONLY a JSON object:
{{
  "follow_up_queries": [
    {{"subtopic": "subtopic title", "query": "more specific query"}}
  ],
  "new_subtopics": [
    {{"title": "new subtopic title", "overview": "brief description"}}
  ]
}}"""
    },

    "question_diversity_check": {
        "zh": """以下是已有的出题角度：
{existing_focuses}

请为主题"{topic}"生成一个与上述角度完全不同的新出题角度。
以 JSON 格式返回：{{"focus": "新的出题角度"}}""",
        "en": """Here are the existing question angles:
{existing_focuses}

Generate a NEW question angle for the topic "{topic}" that is completely different from the existing ones.
Return as JSON: {{"focus": "new question angle"}}"""
    },

    # =============================================================================
    # Guided Learning V2 Prompts (Phase 5 - Checkpoints & Memory)
    # =============================================================================

    "guide_checkpoint_quiz": {
        "zh": """根据知识点"{title}"及其关键概念 {concepts}，生成2道快速检测题来测试学生的理解程度。

以 JSON 格式返回：
{{"questions": [
  {{"question": "问题文本", "answer": "参考答案", "type": "short_answer"}},
  {{"question": "问题文本", "answer": "参考答案", "type": "short_answer"}}
]}}""",
        "en": """Based on the knowledge point "{title}" with key concepts {concepts}, generate 2 quick quiz questions to test understanding.

Return as JSON:
{{"questions": [
  {{"question": "question text", "answer": "reference answer", "type": "short_answer"}},
  {{"question": "question text", "answer": "reference answer", "type": "short_answer"}}
]}}"""
    },

    "guide_evaluate_answer": {
        "zh": """学生对问题"{question}"的回答是："{student_answer}"
参考答案是："{correct_answer}"

判断学生的回答是否可以接受（不需要完全一样，意思正确即可）。
以 JSON 格式返回：{{"passed": true/false, "feedback": "简短反馈"}}""",
        "en": """The student answered "{student_answer}" to the question "{question}".
The correct answer is: "{correct_answer}"

Judge whether the student's answer is acceptable (doesn't need to be exact, just conceptually correct).
Return as JSON: {{"passed": true/false, "feedback": "brief feedback"}}"""
    },

    "guide_consolidate_memory": {
        "zh": """请将以下关于"{title}"的师生对话总结为3-5个关键要点，保留讨论的重点内容和发现的任何误解。

对话内容：
{chat_history}

请直接输出要点总结，不需要JSON格式。""",
        "en": """Summarize the following conversation about "{title}" into 3-5 key takeaways that capture the main points discussed and any misconceptions addressed.

Conversation:
{chat_history}

Output the summary directly, no JSON format needed."""
    },

    # =============================================================================
    # Lecture & Handout Prompts
    # =============================================================================

    "lecture_analyze_kb": {
        "zh": """你是一位教学设计专家。根据以下知识库内容，为主题"{topic}"规划一个讲义/教案结构。

识别4-8个核心章节，每个章节应覆盖一个独立的知识领域。

知识库内容：
{content}

请以JSON格式返回，仅输出JSON：
{{"sections": [{{"title": "章节标题", "instruction": "该章节应涵盖的内容要点"}}]}}""",
        "en": """You are an instructional design expert. Based on the following knowledge base content, plan a lecture/handout structure for the topic "{topic}".

Identify 4-8 core sections, each covering an independent knowledge area.

Knowledge base content:
{content}

Return ONLY a JSON object, no other text:
{{"sections": [{{"title": "section title", "instruction": "key points this section should cover"}}]}}"""
    },

    "lecture_outline": {
        "zh": """你是一位教学设计专家。请优化以下讲义大纲，确定最佳的章节顺序，并为每个章节添加教学重点说明。

主题：{topic}
当前章节列表：
{sections_json}

请以JSON格式返回优化后的大纲，仅输出JSON：
{{"outline": [{{"title": "章节标题", "instruction": "内容要点", "emphasis": "教学重点和过渡说明"}}]}}""",
        "en": """You are an instructional design expert. Refine the following lecture outline, determine optimal section ordering, and add pedagogical emphasis notes for each section.

Topic: {topic}
Current sections:
{sections_json}

Return ONLY a JSON object with the refined outline:
{{"outline": [{{"title": "section title", "instruction": "content points", "emphasis": "teaching emphasis and transition notes"}}]}}"""
    },

    "lecture_write_section": {
        "zh": """你是一位优秀的大学讲师。请为以下讲义章节撰写详细内容。

章节标题：{title}
内容要点：{instruction}
教学重点：{emphasis}

参考资料：
{context}

要求：
1. 使用Markdown格式
2. 结构清晰：概述 → 详细讲解 → 实例说明 → 要点总结
3. 语言通俗易懂，适合教学场景
4. 包含具体的例子和类比
5. 长度适中（300-600字）

请直接输出Markdown内容：""",
        "en": """You are an excellent university lecturer. Write detailed content for the following lecture section.

Section title: {title}
Content points: {instruction}
Teaching emphasis: {emphasis}

Reference material:
{context}

Requirements:
1. Use Markdown format
2. Clear structure: Overview → Detailed explanation → Examples → Key takeaways
3. Clear and accessible language suitable for teaching
4. Include specific examples and analogies
5. Moderate length (300-600 words)

Output the Markdown content directly:"""
    },

    "lecture_summary": {
        "zh": """你是一位教学设计专家。请根据以下讲义各章节的内容摘要，撰写一份简洁的讲义总结/摘要。

各章节概要：
{notes_summary}

要求：
1. 使用Markdown格式
2. 概括讲义的核心主题和关键要点
3. 提供学习建议和延伸阅读方向
4. 长度控制在200-400字

请直接输出Markdown内容：""",
        "en": """You are an instructional design expert. Based on the following section summaries, write a concise lecture summary/abstract.

Section summaries:
{notes_summary}

Requirements:
1. Use Markdown format
2. Summarize core themes and key points
3. Provide study recommendations and further reading directions
4. Keep to 200-400 words

Output the Markdown content directly:"""
    },

    # =============================================================================
    # Exam Paper Prompts
    # =============================================================================

    "exam_plan": {
        "zh": """你是一位考试出题专家。请根据以下知识库内容，为主题"{topic}"规划一份{difficulty}难度的考试结构。

知识库内容：
{context}

要求：
1. 包含多种题型的合理分布
2. 总分应在80-120分之间
3. 考试时长应合理

请以JSON格式返回，仅输出JSON：
{{"sections": [{{"type": "choice|fill_blank|true_false|written", "title": "题型标题", "count": 题目数量, "points_each": 每题分值, "instruction": "出题方向说明"}}], "total_points": 总分, "duration_minutes": 考试时长}}""",
        "en": """You are an exam design expert. Based on the following knowledge base content, plan an exam structure for the topic "{topic}" at {difficulty} difficulty level.

Knowledge base content:
{context}

Requirements:
1. Include a reasonable distribution of question types
2. Total points should be between 80-120
3. Duration should be reasonable

Return ONLY a JSON object, no other text:
{{"sections": [{{"type": "choice|fill_blank|true_false|written", "title": "section title", "count": number_of_questions, "points_each": points_per_question, "instruction": "question focus guidance"}}], "total_points": total, "duration_minutes": duration}}"""
    },

    "exam_generate_section": {
        "zh": """你是一位考试出题专家。请根据以下要求生成考试题目。

题型：{question_type}
数量：{count}
每题分值：{points_each}
难度：{difficulty}
出题方向：{instruction}

参考资料：
{context}

请以JSON格式返回，仅输出JSON：
{{"questions": [{{"question_text": "题目内容", "options": {{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}}, "correct_answer": "正确答案", "explanation": "解析说明", "knowledge_point": "考察知识点"}}]}}

注意：
- choice类型：必须包含4个选项(A/B/C/D)，correct_answer为选项字母
- fill_blank类型：题目中用____标记填空位置，options留空
- true_false类型：correct_answer为"True"或"False"，options留空
- written类型：correct_answer为参考答案要点，options留空""",
        "en": """You are an exam design expert. Generate exam questions based on the following requirements.

Question type: {question_type}
Count: {count}
Points each: {points_each}
Difficulty: {difficulty}
Focus: {instruction}

Reference material:
{context}

Return ONLY a JSON object:
{{"questions": [{{"question_text": "question content", "options": {{"A": "option A", "B": "option B", "C": "option C", "D": "option D"}}, "correct_answer": "correct answer", "explanation": "explanation", "knowledge_point": "tested knowledge point"}}]}}

Note:
- choice type: must include 4 options (A/B/C/D), correct_answer is the option letter
- fill_blank type: use ____ to mark blanks in question_text, options should be empty
- true_false type: correct_answer is "True" or "False", options should be empty
- written type: correct_answer should be key answer points, options should be empty"""
    },

    "exam_answer_key": {
        "zh": """你是一位考试阅卷专家。请根据以下考试题目和答案，生成一份规范的答案与评分标准。

考试内容：
{exam_content}

要求：
1. 使用Markdown格式
2. 按题型分节，标注题号和分值
3. 给出正确答案和简要解析
4. 对于主观题，给出评分要点

请直接输出Markdown内容：""",
        "en": """You are an exam grading expert. Based on the following exam questions and answers, generate a standardized answer key with marking rubric.

Exam content:
{exam_content}

Requirements:
1. Use Markdown format
2. Organize by section, include question numbers and point values
3. Provide correct answers and brief explanations
4. For subjective questions, include marking criteria

Output the Markdown content directly:"""
    },

    "exam_format_header": {
        "zh": """请为以下考试生成一个规范的试卷封面/头部信息。

考试主题：{topic}
总分：{total_points}分
考试时长：{duration_minutes}分钟
题型分布：{sections_summary}

要求：
1. 使用Markdown格式
2. 包含考试名称、总分、时长
3. 包含考生须知/注意事项
4. 包含题型分值概览表

请直接输出Markdown内容：""",
        "en": """Generate a standardized exam cover page/header for the following exam.

Exam topic: {topic}
Total points: {total_points}
Duration: {duration_minutes} minutes
Section breakdown: {sections_summary}

Requirements:
1. Use Markdown format
2. Include exam title, total points, duration
3. Include exam instructions/notes for students
4. Include a section-point breakdown table

Output the Markdown content directly:"""
    },
}
