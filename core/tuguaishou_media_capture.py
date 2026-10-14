"""818ps-only DOM/media capture; all reads use the current browser page."""
def capture_dom_media(driver, previous=()):
    records = driver.execute_script(r"""
        const found = new Map();
        function add(raw, source, el) {
            if (!raw) return;
            let url;
            try { url = new URL(raw, location.href).href; } catch(e) { return; }
            if (!/^(https?:|blob:|data:image\/)/.test(url)) return;
            const rect = el ? el.getBoundingClientRect() : {width:0,height:0};
            const old = found.get(url);
            const record = {url, source, width:rect.width, height:rect.height,
                            isMainPreview:!!(el && rect.width >= 240 && rect.height >= 240 &&
                                el.closest('[class*="preview"],[id*="preview"],[class*="Preview"]')),
                            tagName: el ? el.tagName : '', contentType:el ? (el.type || '') : ''};
            if (!old || rect.width * rect.height > old.width * old.height) found.set(url, record);
        }
        document.querySelectorAll('img,picture source,video,video source').forEach(el => {
            ['src','data-src','poster'].forEach(k => add(el.getAttribute(k), 'dom_'+k, el));
            add(el.currentSrc, 'dom_currentSrc', el);
            // A data URL's comma belongs to its content, not to a srcset delimiter.
            const set = el.getAttribute('srcset') || '';
            if (set.startsWith('data:')) add(set.replace(/\s+\d+[wx]$/, ''), 'dom_srcset', el);
            else set.split(',').forEach(p => add(p.trim().split(/\s+/)[0], 'dom_srcset', el));
        });
        document.querySelectorAll('*').forEach(el => {
            const bg = getComputedStyle(el).backgroundImage;
            for (const m of bg.matchAll(/url\(["']?(.*?)["']?\)/g)) add(m[1], 'dom_background', el);
        });
        performance.getEntriesByType('resource').forEach(e => {
            if (['img','video','fetch','xmlhttprequest'].includes(e.initiatorType))
                add(e.name, 'performance_'+e.initiatorType, null);
        });
        return Array.from(found.values());
    """)
    # Blob URLs die with the browser. Read bounded bytes here, preferring network originals later.
    cached = {r['url']:r for r in previous if r['url'].startswith('blob:') and
              ('bodyBase64' in r or r.get('failureReason'))}
    for record in [r for r in records if r['url'].startswith('blob:')][:4]:
        if record['url'] in cached:
            record.update(cached[record['url']])
            continue
        try:
            data = driver.execute_async_script(r"""
                const url = arguments[0], done = arguments[arguments.length-1];
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 2000);
                fetch(url, {signal:controller.signal}).then(async response => {
                    const readerStream = response.body.getReader(), chunks=[];
                    let size=0;
                    while (true) {
                        const next = await readerStream.read();
                        if (next.done) break;
                        size += next.value.length;
                        if (size > 32*1024*1024) {
                            await readerStream.cancel(); done({failureReason:'size_limit'}); return;
                        }
                        chunks.push(next.value);
                    }
                    const blob = new Blob(chunks, {type:response.headers.get('Content-Type') || ''});
                    const reader = new FileReader();
                    reader.onload = () => done({bodyBase64:reader.result.split(',')[1], contentType:blob.type});
                    reader.onerror = () => done({failureReason:'blob_unavailable'});
                    reader.readAsDataURL(blob);
                }).catch(() => done({failureReason:'blob_unavailable'})).finally(() => clearTimeout(timer));
            """, record['url'])
            record.update(data or {})
        except Exception as error:
            record.update(failureReason='blob_unavailable', exceptionType=type(error).__name__)
    return records
