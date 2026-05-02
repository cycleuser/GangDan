#!/usr/bin/env python
import sys
sys.path.insert(0, '.')

print("Testing imports...")
try:
    from gangdan.core.config import CONFIG, TRANSLATIONS, t
    print("OK: config imported")
    print(f"  Language: {CONFIG.language}")
    print(f"  Translations count: {len(TRANSLATIONS)}")
except Exception as e:
    print(f"FAIL: config import: {e}")
    sys.exit(1)

print("\nTesting new translation keys...")
required_keys = [
    'upload_mode', 'upload_mode_files', 'upload_mode_folder',
    'select_folder', 'folder_upload_desc', 'output_length',
    'output_length_desc', 'words', 'system_monitor',
    'context_length', 'max_context', 'memory_usage',
    'kb_docs', 'documents'
]
missing = []
for key in required_keys:
    if key not in TRANSLATIONS:
        missing.append(key)
    else:
        print(f"  OK: {key} -> {t(key)}")

if missing:
    print(f"FAIL: Missing translation keys: {missing}")
    sys.exit(1)

print("\nTesting doc_manager...")
try:
    from gangdan.core.doc_manager import DOC_MANAGER
    print("OK: doc_manager imported")
except Exception as e:
    print(f"FAIL: doc_manager import: {e}")
    sys.exit(1)

print("\nTesting image_handler...")
try:
    from gangdan.core.image_handler import ImageHandler
    print("OK: image_handler imported")
except Exception as e:
    print(f"FAIL: image_handler import: {e}")
    sys.exit(1)

print("\nAll basic tests passed!")