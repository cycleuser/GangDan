"""Preprint platform category definitions.

Defines the category/taxonomy systems for each preprint platform:
- arXiv: Hierarchical CS/Math/Physics categories
- bioRxiv: Biology subject collections
- medRxiv: Medical/Health subject collections

Each category has:
- code: Platform-specific identifier
- name: Display name (English)
- name_zh: Chinese display name
- description: Brief description
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Category:
    """A single category from a preprint platform.

    Attributes
    ----------
    code : str
        Platform-specific category code.
    name : str
        English display name.
    name_zh : str
        Chinese display name.
    description : str
        Brief description of the category.
    parent : str
        Parent category code (empty for top-level).
    """

    code: str = ""
    name: str = ""
    name_zh: str = ""
    description: str = ""
    parent: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "name": self.name,
            "name_zh": self.name_zh,
            "description": self.description,
            "parent": self.parent,
        }


# arXiv categories (major groups)
ARXIV_CATEGORIES: List[Category] = [
    # Computer Science
    Category("cs.AI", "Artificial Intelligence", "人工智能", "Machine learning, NLP, computer vision, robotics"),
    Category("cs.LG", "Machine Learning", "机器学习", "Deep learning, reinforcement learning, optimization"),
    Category("cs.CL", "Computation and Language", "计算语言学", "NLP, speech processing, machine translation"),
    Category("cs.CV", "Computer Vision", "计算机视觉", "Image processing, object detection, 3D vision"),
    Category("cs.RO", "Robotics", "机器人学", "Motion planning, control, perception, manipulation"),
    Category("cs.SE", "Software Engineering", "软件工程", "Program analysis, testing, formal methods"),
    Category("cs.DB", "Databases", "数据库", "Data models, query processing, distributed databases"),
    Category("cs.CR", "Cryptography and Security", "密码学与安全", "Network security, privacy, cryptographic protocols"),
    Category("cs.HC", "Human-Computer Interaction", "人机交互", "User interfaces, accessibility, CSCW"),
    Category("cs.IR", "Information Retrieval", "信息检索", "Search engines, recommendation systems, ranking"),
    Category("cs.NE", "Neural and Evolutionary Computing", "神经与进化计算", "Neural networks, genetic algorithms"),
    Category("cs.OS", "Operating Systems", "操作系统", "Process management, memory, file systems"),
    Category("cs.PL", "Programming Languages", "编程语言", "Type systems, compilers, semantics"),
    Category("cs.DC", "Distributed, Parallel, and Cluster Computing", "分布式与并行计算", "Cloud computing, distributed systems, HPC"),
    Category("cs.NI", "Networking and Internet Architecture", "网络与互联网架构", "Network protocols, SDN, IoT"),
    Category("cs.DS", "Data Structures and Algorithms", "数据结构与算法", "Algorithm design, complexity, graph algorithms"),
    Category("cs.MA", "Multiagent Systems", "多智能体系统", "Game theory, mechanism design, agent coordination"),
    Category("cs.AR", "Hardware Architecture", "硬件架构", "CPU/GPU design, memory hierarchy, embedded systems"),
    Category("cs.ET", "Emerging Technologies", "新兴技术", "Quantum computing, nanotechnology, DNA computing"),
    Category("cs.SI", "Social and Information Networks", "社交与信息网络", "Social network analysis, graph mining"),

    # Mathematics
    Category("math.ST", "Statistics Theory", "统计学理论", "Statistical inference, hypothesis testing"),
    Category("math.OC", "Optimization and Control", "优化与控制", "Convex optimization, optimal control"),
    Category("math.PR", "Probability", "概率论", "Stochastic processes, random matrices"),

    # Physics
    Category("physics.data-an", "Data Analysis, Statistics and Probability", "数据分析与统计", "Statistical methods for physics data"),
    Category("cond-mat.mtrl-sci", "Materials Science", "材料科学", "Computational materials, crystallography"),
    Category("quant-ph", "Quantum Physics", "量子物理", "Quantum information, quantum computing"),
    Category("astro-ph", "Astrophysics", "天体物理学", "Stellar evolution, cosmology, galaxies"),
    Category("hep-ph", "High Energy Physics - Phenomenology", "高能物理现象学", "Particle physics models, collider phenomenology"),
    Category("nucl-th", "Nuclear Theory", "核理论", "Nuclear structure, reactions, QCD"),

    # Biology
    Category("q-bio", "Quantitative Biology", "定量生物学", "Computational biology, systems biology"),
    Category("q-bio.GN", "Genomics", "基因组学", "Genome analysis, sequencing, annotation"),
    Category("q-bio.NC", "Neurons and Cognition", "神经与认知", "Computational neuroscience, cognitive modeling"),
    Category("q-bio.QM", "Quantitative Methods", "定量方法", "Statistical methods for biology"),

    # Economics
    Category("econ.EM", "Econometrics", "计量经济学", "Time series analysis, panel data"),
    Category("econ.GN", "General Economics", "一般经济学", "Economic theory, policy analysis"),

    # Electrical Engineering
    Category("eess.SP", "Signal Processing", "信号处理", "Audio/image processing, communications"),
    Category("eess.SY", "Systems and Control", "系统与控制", "Control theory, system identification"),

    # Statistics
    Category("stat.ML", "Machine Learning (Statistics)", "机器学习（统计）", "Statistical learning theory, Bayesian methods"),
    Category("stat.ME", "Methodology", "方法论", "Study design, sampling, experimental methods"),
    Category("stat.AP", "Applications", "应用领域", "Biostatistics, environmental statistics"),
]

# bioRxiv collections
BIORXIV_CATEGORIES: List[Category] = [
    Category("bioinformatics", "Bioinformatics", "生物信息学", "Computational biology, genomics tools, sequence analysis"),
    Category("genomics", "Genomics", "基因组学", "Genome sequencing, assembly, annotation, comparative genomics"),
    Category("molecular_biology", "Molecular Biology", "分子生物学", "Gene expression, protein function, signaling pathways"),
    Category("neuroscience", "Neuroscience", "神经科学", "Brain function, neural circuits, behavior, cognition"),
    Category("cell_biology", "Cell Biology", "细胞生物学", "Cell structure, division, differentiation, organelles"),
    Category("developmental_biology", "Developmental Biology", "发育生物学", "Embryogenesis, tissue development, stem cells"),
    Category("ecology", "Ecology", "生态学", "Population dynamics, ecosystems, biodiversity, conservation"),
    Category("evolutionary_biology", "Evolutionary Biology", "进化生物学", "Natural selection, phylogenetics, speciation"),
    Category("immunology", "Immunology", "免疫学", "Immune system, antibodies, vaccines, inflammation"),
    Category("microbiology", "Microbiology", "微生物学", "Bacteria, viruses, fungi, host-pathogen interactions"),
    Category("physiology", "Physiology", "生理学", "Organ function, metabolism, homeostasis"),
    Category("plant_biology", "Plant Biology", "植物生物学", "Plant genetics, photosynthesis, crop science"),
    Category("synthetic_biology", "Synthetic Biology", "合成生物学", "Genetic engineering, metabolic engineering, biodesign"),
    Category("systems_biology", "Systems Biology", "系统生物学", "Network biology, modeling, omics integration"),
    Category("zoology", "Zoology", "动物学", "Animal behavior, physiology, taxonomy"),
    Category("anatomy", "Anatomy", "解剖学", "Structural biology, morphology, histology"),
    Category("biophysics", "Biophysics", "生物物理学", "Molecular dynamics, structural biology, single-molecule"),
    Category("cancer_biology", "Cancer Biology", "癌症生物学", "Oncogenesis, tumor microenvironment, therapy resistance"),
    Category("epidemiology", "Epidemiology", "流行病学", "Disease transmission, public health, outbreak analysis"),
    Category("genetics", "Genetics", "遗传学", "Gene mapping, GWAS, heritability, epigenetics"),
    Category("pathology", "Pathology", "病理学", "Disease mechanisms, histopathology, diagnostics"),
    Category("pharmacology", "Pharmacology", "药理学", "Drug discovery, pharmacokinetics, toxicology"),
    Category("toxicology", "Toxicology", "毒理学", "Chemical safety, environmental toxins, risk assessment"),
]

# medRxiv collections
MEDRXIV_CATEGORIES: List[Category] = [
    Category("cardiovascular_medicine", "Cardiovascular Medicine", "心血管医学", "Heart disease, hypertension, stroke, vascular disorders"),
    Category("dentistry", "Dentistry", "口腔医学", "Oral health, dental surgery, orthodontics"),
    Category("dermatology", "Dermatology", "皮肤病学", "Skin diseases, wound healing, cosmetic dermatology"),
    Category("emergency_medicine", "Emergency Medicine", "急诊医学", "Trauma care, critical care, disaster medicine"),
    Category("endocrinology", "Endocrinology", "内分泌学", "Diabetes, thyroid disorders, hormone therapy"),
    Category("epidemiology", "Epidemiology", "流行病学", "Disease surveillance, outbreak investigation, public health"),
    Category("forensic_medicine", "Forensic Medicine", "法医学", "Forensic pathology, DNA analysis, toxicology"),
    Category("gastroenterology", "Gastroenterology", "胃肠病学", "Digestive diseases, liver disorders, nutrition"),
    Category("genetic_genomic_medicine", "Genetic & Genomic Medicine", "遗传与基因组医学", "Precision medicine, gene therapy, pharmacogenomics"),
    Category("geriatric_medicine", "Geriatric Medicine", "老年医学", "Aging, dementia, age-related diseases"),
    Category("health_economics", "Health Economics", "卫生经济学", "Cost-effectiveness, healthcare policy, insurance"),
    Category("health_informatics", "Health Informatics", "健康信息学", "EHR, telemedicine, AI in healthcare, data analytics"),
    Category("health_policy", "Health Policy", "卫生政策", "Healthcare reform, regulation, access to care"),
    Category("hematology", "Hematology", "血液学", "Blood disorders, anemia, coagulation, transfusion"),
    Category("hiv_aids", "HIV/AIDS", "艾滋病", "Antiretroviral therapy, prevention, vaccine development"),
    Category("infectious_diseases", "Infectious Diseases", "传染病", "Viral, bacterial, fungal, parasitic infections"),
    Category("intensive_care", "Intensive Care Medicine", "重症医学", "ICU management, mechanical ventilation, sepsis"),
    Category("medical_education", "Medical Education", "医学教育", "Curriculum design, simulation, assessment"),
    Category("nephrology", "Nephrology", "肾脏病学", "Kidney disease, dialysis, transplantation"),
    Category("neurology", "Neurology", "神经病学", "Stroke, epilepsy, neurodegenerative diseases"),
    Category("obstetrics_gynecology", "Obstetrics & Gynecology", "妇产科学", "Pregnancy, reproductive health, maternal-fetal medicine"),
    Category("occupational_health", "Occupational Health", "职业健康", "Workplace safety, ergonomics, occupational diseases"),
    Category("oncology", "Oncology", "肿瘤学", "Cancer treatment, immunotherapy, clinical trials"),
    Category("ophthalmology", "Ophthalmology", "眼科学", "Vision, eye diseases, surgery, optics"),
    Category("orthopedics", "Orthopedics", "骨科学", "Bone/joint diseases, sports medicine, rehabilitation"),
    Category("otolaryngology", "Otolaryngology", "耳鼻喉科学", "Hearing, balance, sinus disorders"),
    Category("palliative_medicine", "Palliative Medicine", "姑息医学", "Pain management, end-of-life care, quality of life"),
    Category("pathology", "Pathology", "病理学", "Diagnostic pathology, molecular diagnostics, autopsy"),
    Category("pediatrics", "Pediatrics", "儿科学", "Child health, neonatal care, developmental disorders"),
    Category("pharmacology_therapeutics", "Pharmacology & Therapeutics", "药理学与治疗学", "Clinical trials, drug safety, personalized medicine"),
    Category("primary_care", "Primary Care", "初级保健", "Family medicine, community health, preventive care"),
    Category("psychiatry", "Psychiatry", "精神病学", "Mental health, depression, schizophrenia, addiction"),
    Category("public_global_health", "Public & Global Health", "公共卫生与全球健康", "Health equity, global health initiatives, disease prevention"),
    Category("radiology_imaging", "Radiology & Imaging", "放射学与影像", "MRI, CT, ultrasound, image-guided therapy"),
    Category("rehabilitation", "Rehabilitation", "康复医学", "Physical therapy, occupational therapy, prosthetics"),
    Category("respiratory_medicine", "Respiratory Medicine", "呼吸医学", "Asthma, COPD, pulmonary fibrosis, sleep apnea"),
    Category("rheumatology", "Rheumatology", "风湿病学", "Arthritis, autoimmune diseases, connective tissue disorders"),
    Category("sports_medicine", "Sports Medicine", "运动医学", "Exercise physiology, injury prevention, performance"),
    Category("surgery", "Surgery", "外科学", "Surgical techniques, minimally invasive surgery, outcomes"),
    Category("toxicology", "Toxicology", "毒理学", "Poisoning, environmental health, risk assessment"),
    Category("transplantation", "Transplantation", "移植医学", "Organ transplant, immunosuppression, rejection"),
    Category("urology", "Urology", "泌尿外科学", "Kidney stones, prostate disease, urologic oncology"),
]


# Platform metadata
PLATFORMS = {
    "arxiv": {
        "name": "arXiv",
        "name_zh": "arXiv",
        "description": "Physics, Mathematics, Computer Science, Quantitative Biology, etc.",
        "description_zh": "物理、数学、计算机、定量生物学等",
        "categories": ARXIV_CATEGORIES,
    },
    "biorxiv": {
        "name": "bioRxiv",
        "name_zh": "bioRxiv",
        "description": "Life Sciences and Biology",
        "description_zh": "生命科学与生物学",
        "categories": BIORXIV_CATEGORIES,
    },
    "medrxiv": {
        "name": "medRxiv",
        "name_zh": "medRxiv",
        "description": "Health Sciences and Medicine",
        "description_zh": "健康科学与医学",
        "categories": MEDRXIV_CATEGORIES,
    },
}


def get_platform_categories(platform: str) -> List[Category]:
    """Get categories for a specific platform.

    Parameters
    ----------
    platform : str
        Platform name: 'arxiv', 'biorxiv', 'medrxiv'.

    Returns
    -------
    List[Category]
        List of categories for the platform.
    """
    if platform in PLATFORMS:
        return PLATFORMS[platform]["categories"]
    return []


def get_all_categories() -> Dict[str, List[dict]]:
    """Get all categories for all platforms as dictionaries.

    Returns
    -------
    Dict[str, List[dict]]
        Mapping of platform name to category list.
    """
    result = {}
    for platform, info in PLATFORMS.items():
        result[platform] = {
            "name": info["name"],
            "name_zh": info["name_zh"],
            "description": info["description"],
            "description_zh": info["description_zh"],
            "categories": [c.to_dict() for c in info["categories"]],
        }
    return result


def search_categories(query: str, platform: Optional[str] = None) -> List[dict]:
    """Search categories by query across platforms.

    Parameters
    ----------
    query : str
        Search query (matches code, name, name_zh, description).
    platform : str or None
        Limit search to specific platform.

    Returns
    -------
    List[dict]
        Matching categories with platform info.
    """
    results = []
    query_lower = query.lower()

    platforms_to_search = [platform] if platform else PLATFORMS.keys()

    for plat in platforms_to_search:
        if plat not in PLATFORMS:
            continue
        for cat in PLATFORMS[plat]["categories"]:
            if (
                query_lower in cat.code.lower()
                or query_lower in cat.name.lower()
                or query_lower in cat.name_zh
                or query_lower in cat.description.lower()
            ):
                result = cat.to_dict()
                result["platform"] = plat
                result["platform_name"] = PLATFORMS[plat]["name"]
                results.append(result)

    return results


def get_category_by_code(code: str, platform: str) -> Optional[Category]:
    """Get a specific category by code.

    Parameters
    ----------
    code : str
        Category code (e.g., 'cs.AI').
    platform : str
        Platform name.

    Returns
    -------
    Category or None
        The category if found.
    """
    for cat in get_platform_categories(platform):
        if cat.code == code:
            return cat
    return None
