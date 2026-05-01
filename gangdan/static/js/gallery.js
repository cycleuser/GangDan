/**
 * Image Gallery Module / 图片画廊模块
 * Handles browsing, searching, and viewing images from knowledge bases
 * 处理知识库图片的浏览、搜索和查看
 */

const GalleryModule = {
    currentKb: null,
    images: [],
    
    getT(key) {
        // Use global i18n if available, fallback to local translations
        if (typeof getT === 'function') {
            return getT(key);
        }
        const lang = window.SERVER_CONFIG?.lang || 'en';
        const fallback = {
            select_kb: 'Select KB',
            search_images: 'Search images...',
            search: 'Search',
            images_from: 'images from',
            sources: 'sources',
            untitled: 'Untitled',
            unknown: 'Unknown',
            no_images: 'No images found',
            select_kb_first: 'Please select a knowledge base first',
            source: 'Source',
            file: 'File',
            kb: 'KB',
            loading: 'Loading...',
            failed_load: 'Failed to load',
            image_gallery: 'Image Gallery',
            all_images: 'All Images',
            show_context: 'Show Context',
            hide_context: 'Hide Context',
            prev: 'Previous',
            next: 'Next',
            browse: 'Browse',
        };
        return fallback[key] || key;
    },
    
    init() {
        this.loadKbList();
    },
    
    async loadKbList() {
        try {
            const res = await fetch('/api/kb/list');
            const data = await res.json();
            const select = document.getElementById('galleryKbSelect');
            select.innerHTML = `<option value="">${this.getT('select_kb')}</option>`;
            
            data.kbs.forEach(kb => {
                const option = document.createElement('option');
                option.value = kb.name;
                option.textContent = `${kb.display_name} (${kb.doc_count} docs)`;
                select.appendChild(option);
            });
            
            // Auto-load gallery when KB is selected
            select.addEventListener('change', () => this.loadGallery());
        } catch (err) {
            console.error('Failed to load KB list:', err);
        }
    },
    
    async loadGallery() {
        const kbName = document.getElementById('galleryKbSelect').value;
        console.log('[Gallery] Loading gallery for KB:', kbName);
        
        if (!kbName) {
            document.getElementById('galleryGrid').innerHTML = '';
            document.getElementById('galleryEmpty').style.display = 'block';
            document.getElementById('galleryEmpty').innerHTML = `
                <p style="font-size:3em; margin:0;">📷</p>
                <p>${this.getT('select_kb_first')}</p>
            `;
            document.getElementById('galleryStats').textContent = '';
            this.currentKb = null;
            this.images = [];
            return;
        }
        
        this.currentKb = kbName;
        
        // Show loading state
        const grid = document.getElementById('galleryGrid');
        grid.innerHTML = `<p style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted);">${this.getT('loading')}</p>`;
        document.getElementById('galleryEmpty').style.display = 'none';
        
        try {
            const url = `/api/kb/gallery?name=${encodeURIComponent(kbName)}&group_by=source_file`;
            console.log('[Gallery] Fetching:', url);
            
            const res = await fetch(url);
            const data = await res.json();
            console.log('[Gallery] Response:', data);
            
            if (!data.success) {
                console.error('[Gallery] Error:', data.error);
                let errorMsg = data.error || this.getT('failed_load');
                
                // Show available KBs if returned
                if (data.available_kbs && data.available_kbs.length > 0) {
                    errorMsg += `. Available: ${data.available_kbs.join(', ')}`;
                }
                
                showToast(errorMsg, 'error');
                grid.innerHTML = '';
                document.getElementById('galleryEmpty').style.display = 'block';
                document.getElementById('galleryEmpty').innerHTML = `
                    <p style="font-size:3em; margin:0;">⚠️</p>
                    <p>${errorMsg}</p>
                `;
                return;
            }
            
            this.images = [];
            grid.innerHTML = '';
            
            // Update stats - show immediately even if no images
            document.getElementById('galleryStats').textContent = 
                `${data.total_images} ${this.getT('images_from')} ${data.total_sources} ${this.getT('sources')}`;
            
            if (data.total_images === 0 || !data.gallery || data.gallery.length === 0) {
                document.getElementById('galleryEmpty').style.display = 'block';
                document.getElementById('galleryEmpty').innerHTML = `
                    <p style="font-size:3em; margin:0;">📷</p>
                    <p>${this.getT('no_images')}</p>
                `;
                return;
            }
            
            document.getElementById('galleryEmpty').style.display = 'none';
            
            // Group by source file and display ALL images
            data.gallery.forEach(source => {
                // Add source header
                const header = document.createElement('div');
                header.style.gridColumn = '1 / -1';
                header.style.marginTop = '15px';
                header.style.padding = '10px';
                header.style.background = 'var(--bg-secondary)';
                header.style.borderRadius = '4px';
                header.innerHTML = `<strong>📄 ${source.source_file}</strong> (${source.count} images)`;
                grid.appendChild(header);
                
                // Add ALL images from this source
                if (source.images && source.images.length > 0) {
                    source.images.forEach(img => {
                        this.images.push(img);
                        const card = this.createImageCard(img, kbName);
                        grid.appendChild(card);
                    });
                }
            });
        } catch (err) {
            console.error('Failed to load gallery:', err);
            showToast(this.getT('failed_load'), 'error');
            grid.innerHTML = '';
            document.getElementById('galleryEmpty').style.display = 'block';
        }
    },
    
    createImageCard(img, kbName) {
        const card = document.createElement('div');
        card.className = 'image-card';
        card.style.cssText = `
            background: var(--bg-secondary);
            border-radius: 8px;
            overflow: hidden;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        `;
        card.onmouseover = () => {
            card.style.transform = 'translateY(-2px)';
            card.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
        };
        card.onmouseout = () => {
            card.style.transform = 'translateY(0)';
            card.style.boxShadow = 'none';
        };
        card.onclick = () => this.showImageModal(img, kbName);
        
        const imgUrl = `/api/kb/image/${encodeURIComponent(kbName)}/${img.path}`;
        const altText = img.alt_text || this.getT('untitled');
        
        card.innerHTML = `
            <div style="height:150px; background:var(--bg-tertiary); display:flex; align-items:center; justify-content:center; overflow:hidden;">
                <img src="${imgUrl}" alt="${altText}" 
                     style="width:100%; height:100%; object-fit:cover;"
                     loading="lazy"
                     onerror="this.parentElement.innerHTML='<span style=\\'color:var(--text-muted);font-size:3em;\\'>🖼️</span>'">
            </div>
            <div style="padding:10px;">
                <p style="margin:0 0 5px 0; font-size:0.85em; font-weight:600; color:var(--text-primary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${altText}">
                    ${altText}
                </p>
                <p style="margin:0; font-size:0.75em; color:var(--text-muted);">
                    📄 ${img.source_file || this.getT('unknown')}
                </p>
            </div>
        `;
        
        return card;
    },
    
    showImageModal(img, kbName) {
        const modal = document.getElementById('imageModal');
        const modalImg = document.getElementById('imageModalImg');
        const imgUrl = `/api/kb/image/${encodeURIComponent(kbName)}/${img.path}`;
        
        modalImg.src = imgUrl;
        modalImg.alt = img.alt_text || this.getT('untitled');
        document.getElementById('imageModalTitle').textContent = img.alt_text || this.getT('untitled');
        document.getElementById('imageModalSource').textContent = `${this.getT('source')}: ${img.source_file || this.getT('unknown')}`;
        document.getElementById('imageModalFile').textContent = `${this.getT('file')}: ${img.name || img.path}`;
        document.getElementById('imageModalKb').textContent = `${this.getT('kb')}: ${kbName}`;
        
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }
};

function closeImageModal() {
    document.getElementById('imageModal').style.display = 'none';
    document.body.style.overflow = '';
}

// Handle escape key to close modal
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeImageModal();
    }
});

// Initialize gallery when module loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => GalleryModule.init());
} else {
    GalleryModule.init();
}

// Override showPanel to init gallery when clicked
if (window.showPanel) {
    const originalShowPanel = window.showPanel;
    window.showPanel = function(panelName, tab) {
        originalShowPanel(panelName, tab);
        if (panelName === 'gallery') {
            // Re-load gallery if KB is already selected
            const kbSelect = document.getElementById('galleryKbSelect');
            if (kbSelect && kbSelect.value) {
                GalleryModule.loadGallery();
            }
        }
    };
}

// Search with advanced context matching
async function searchGalleryAdvanced() {
    const query = document.getElementById('gallerySearchInput').value.trim();
    const searchType = document.getElementById('gallerySearchType').value;
    
    if (!query) {
        loadGallery(); // Show all if no query
        return;
    }
    
    const kbName = document.getElementById('galleryKbSelect').value;
    if (!kbName) {
        showToast(GalleryModule.getT('select_kb_first'), 'error');
        return;
    }
    
    const grid = document.getElementById('galleryGrid');
    grid.innerHTML = `<p style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted);">${GalleryModule.getT('loading')}</p>`;
    
    try {
        const response = await fetch('/api/kb/images/search-advanced', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                kb_name: kbName,
                query: query,
                search_type: searchType,
                limit: 50
            })
        });
        
        const data = await response.json();
        
        if (!data.success) {
            showToast(data.error || GalleryModule.getT('failed_load'), 'error');
            grid.innerHTML = '';
            return;
        }
        
        document.getElementById('galleryStats').textContent = 
            `${data.count} ${GalleryModule.getT('images_from')} "${query}"`;
        
        if (data.count === 0) {
            grid.innerHTML = `<p style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted);">${GalleryModule.getT('no_images')}</p>`;
            return;
        }
        
        grid.innerHTML = '';
        
        // Group by source file
        const grouped = {};
        data.images.forEach(img => {
            const source = img.source_file || 'unknown';
            if (!grouped[source]) {
                grouped[source] = [];
            }
            grouped[source].push(img);
        });
        
        // Display grouped results
        Object.keys(grouped).sort().forEach(source => {
            // Source header
            const header = document.createElement('div');
            header.style.gridColumn = '1 / -1';
            header.style.marginTop = '15px';
            header.style.padding = '10px';
            header.style.background = 'var(--bg-secondary)';
            header.style.borderRadius = '4px';
            header.innerHTML = `<strong>📄 ${source}</strong> (${grouped[source].length} images)`;
            grid.appendChild(header);
            
            // Images
            grouped[source].forEach(img => {
                GalleryModule.images.push(img);
                const card = createImageCardWithContent(img, kbName);
                grid.appendChild(card);
            });
        });
    } catch (err) {
        console.error('Advanced search failed:', err);
        showToast(GalleryModule.getT('failed_load'), 'error');
    }
}

// Keep old search function for backward compatibility
function searchGallery() {
    searchGalleryAdvanced();
}

// Create image card with context
function createImageCardWithContent(img, kbName) {
    const card = document.createElement('div');
    card.className = 'image-card';
    card.style.cssText = `
        background: var(--bg-secondary);
        border-radius: 8px;
        overflow: hidden;
        cursor: pointer;
        transition: transform 0.2s, box-shadow 0.2s;
        display: flex;
        flex-direction: column;
    `;
    card.onmouseover = () => {
        card.style.transform = 'translateY(-2px)';
        card.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
    };
    card.onmouseout = () => {
        card.style.transform = 'translateY(0)';
        card.style.boxShadow = 'none';
    };
    card.onclick = (e) => {
        if (!e.target.classList.contains('show-context')) {
            GalleryModule.showImageModal(img, kbName);
        }
    };
    
    const imgUrl = `/api/kb/image/${encodeURIComponent(kbName)}/${img.path}`;
    const altText = img.alt_text || GalleryModule.getT('untitled');
    const score = img.relevance_score || 0;
    
    card.innerHTML = `
        <div style="height:150px; background:var(--bg-tertiary); display:flex; align-items:center; justify-content:center; overflow:hidden; position:relative;">
            <img src="${imgUrl}" alt="${altText}" 
                 style="width:100%; height:100%; object-fit:cover;"
                 loading="lazy"
                 onerror="this.parentElement.innerHTML='<span style=\\'color:var(--text-muted);font-size:3em;\\'>🖼️</span>'">
            ${score > 0 ? `<span style="position:absolute;top:5px;right:5px;background:var(--primary);color:white;padding:2px 6px;border-radius:3px;font-size:0.7em;font-weight:bold;">Score: ${score}</span>` : ''}
        </div>
        <div style="padding:10px;flex:1;">
            <p style="margin:0 0 5px 0; font-size:0.85em; font-weight:600; color:var(--text-primary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${altText}">
                ${altText}
            </p>
            <p style="margin:0 0 5px 0; font-size:0.75em; color:var(--text-muted);">
                📄 ${img.source_file || GalleryModule.getT('unknown')}
            </p>
            ${img.context_before ? `
                <div style="margin-top:8px;padding:8px;background:var(--bg-tertiary);border-radius:4px;font-size:0.75em;color:var(--text-muted);max-height:80px;overflow:hidden;">
                    <strong>Context:</strong> ${img.context_before.substring(0, 150)}...
                </div>
            ` : ''}
            <button class="show-context" onclick="event.stopPropagation(); toggleContext(this)" 
                    style="margin-top:8px;padding:4px 8px;font-size:0.75em;background:var(--primary);color:white;border:none;border-radius:4px;cursor:pointer;">
                ${GalleryModule.getT('show_context') || '查看上下文'}
            </button>
        </div>
    `;
    
    // Store full context for toggle
    card.dataset.fullContextBefore = img.context_before || '';
    card.dataset.fullContextAfter = img.context_after || '';
    
    return card;
}

// Toggle context display
function toggleContext(btn) {
    const card = btn.closest('.image-card');
    const existingDetail = card.querySelector('.context-detail');
    
    if (existingDetail) {
        existingDetail.remove();
        btn.textContent = GalleryModule.getT('show_context') || '查看上下文';
    } else {
        const contextBefore = card.dataset.fullContextBefore || '';
        const contextAfter = card.dataset.fullContextAfter || '';
        
        const detail = document.createElement('div');
        detail.className = 'context-detail';
        detail.style.cssText = 'margin-top:8px;padding:8px;background:var(--bg-tertiary);border-radius:4px;font-size:0.75em;color:var(--text);';
        detail.innerHTML = `
            ${contextBefore ? `<div style="margin-bottom:8px;"><strong style="color:var(--primary);">Before:</strong><br>${contextBefore}</div>` : ''}
            ${contextAfter ? `<div><strong style="color:var(--primary);">After:</strong><br>${contextAfter}</div>` : ''}
        `;
        
        card.insertBefore(detail, btn.nextSibling);
        btn.textContent = GalleryModule.getT('hide_context') || '隐藏上下文';
    }
}
