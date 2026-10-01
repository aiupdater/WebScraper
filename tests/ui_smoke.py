"""Offline UI checks. Run: python tests/ui_smoke.py [Chromium executable]."""
import functools
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from system.browser_fetcher import BrowserFetcher
from system.core import Config, search_profiles


def portal_navigation_smoke(browser):
    """Real browser navigation: second page only works after the POST form."""
    context = browser.new_context()
    requests = []
    profile = '/branchenbuch/dortmund/123B456/acme.html'
    listing = f'<h1>Results</h1><a href="{profile}">Mehr Details</a>'
    form = '<form action="https://www.11880.com/form" method="POST"><button aria-label="Zur nächsten Seite">Next</button></form>'
    def respond(route):
        request = route.request
        requests.append((request.method, request.url))
        if request.url.endswith('/form'):
            # Playwright neinterceptuje navazující HTTP přesměrování. URL změní
            # lokální fixture, aby test nemohl přejít na skutečný veřejný web.
            route.fulfill(status=200, content_type='text/html; charset=utf-8',
                          body=listing + '<script>history.replaceState(null,"","/suche/Tiefbau/deutschland?page=2")</script>')
        elif '?page=2' in request.url:
            allowed = any(method == 'POST' for method, _ in requests)
            route.fulfill(status=200 if allowed else 403, content_type='text/html; charset=utf-8', body=listing)
        else:
            route.fulfill(status=200, content_type='text/html; charset=utf-8', body=listing + form)
    context.route('**/*', respond)
    from types import SimpleNamespace
    http = SimpleNamespace(validate_target=lambda url: None, pace=lambda url: None)
    fetch = BrowserFetcher(Config(portal='11880'), threading.Event(), lambda *a, **kw: None,
                           ROOT/'tests'/'artifacts', threading.Event(), http, context_factory=lambda: context)
    try:
        html, final = fetch.get('https://www.11880.com/suche/Tiefbau/deutschland?page=2')
        assert final.endswith('?page=2')
        assert len(search_profiles(html, final, '11880')) == 1
        assert ('POST', 'https://www.11880.com/form') in requests
    finally:
        fetch.close()

MOCK = """window.events=[]; window.pywebview={api:{
bootstrap:async()=>({ok:true,categories:['Tiefbau','Abbruch'],folder:'test-results',settings:{has_password:true}}),
folder_info:async()=>({ok:true,resume:false}),
settings_password:async()=>({ok:true,password:'test-password'}),
poll_events:async()=>window.events.splice(0,150),
start_run:async(c)=>{window.lastConfig=c;return {ok:true,folder:c.folder}},
save_categories:async(c)=>({ok:true,categories:c}),
stop_run:async()=>{events.push({type:'finish',status:'STOPPED',profiles:80,emails:80,skipped_existing:0,errors_this_run:0,review:0,folder:'test-results',mysql:{}},{type:'idle'});return {ok:true}},
finish_run:async(c)=>{window.lastFinishConfig=c;events.push({type:'finish',status:'DONE',profiles:80,emails:80,skipped_existing:0,errors_this_run:0,review:0,folder:'test-results',mysql:{INSERTED:80}});return {ok:true,folder:c.folder}},
discard_saved_run:async()=>{events.push({type:'discarded',folder:'test-results'});return {ok:true}},
new_folder:async()=>({ok:true,folder:'new-test-results'}),
confirm_verification:async()=>({ok:true}),
connect_database:async()=>{window.events.push({type:'groups',groups:[[1,'Tiefbau']]});return {ok:true}}
}};"""


def delayed_bridge_smoke(browser, url):
    """Optional portal hint must not prevent late Python bridge initialization."""
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    html = (ROOT/'ui/index.html').read_text(encoding='utf-8')
    html = re.sub(r'<p[^>]*id="portal-help"[^>]*>.*?</p>', '', html)
    page.route(url, lambda route: route.fulfill(content_type='text/html; charset=utf-8', body=html))
    page.add_init_script('setTimeout(() => {' + MOCK +
                         'window.dispatchEvent(new Event("pywebviewready"));}, 500);')
    try:
        page.goto(url)
        expect(page.locator('#start')).to_be_enabled()
        page.select_option('#portal', '11880')
        page.click('#new-folder')
        expect(page.locator('#folder')).to_have_value('new-test-results')
        page.click('#mysql-toggle')
        expect(page.locator('#db-password')).to_have_value('test-password')
        assert not errors, errors
    finally:
        page.close()


def startup_loader_smoke(browser, url):
    """Startup reports live phases and waits for the initial MySQL result."""
    page = browser.new_page(reduced_motion='no-preference')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.add_init_script("""window.events=[]; window.pywebview={api:{
bootstrap:async()=>{await new Promise(r=>setTimeout(r,350));return {ok:true,categories:['Tiefbau'],folder:'test-results',settings:{has_password:true}}},
folder_info:async()=>({ok:true,resume:false}),
poll_events:async()=>window.events.splice(0,50),
connect_database:async()=>{setTimeout(()=>window.events.push({type:'groups',groups:[[1,'Tiefbau']]}),450);return {ok:true}},
settings_password:async()=>({ok:true,password:'test-password'}),
save_categories:async(c)=>({ok:true,categories:c})
}};""")
    try:
        page.goto(url)
        expect(page.locator('#startup-loader')).to_be_visible()
        expect(page.locator('#startup-percent')).to_contain_text('%')
        expect(page.locator('#startup-phase')).to_contain_text('Python')
        expect(page.locator('#startup-phase')).to_contain_text('EmailApp', timeout=3000)
        expect(page.locator('#startup-progress')).to_have_attribute('aria-valuenow', '78')
        page.screenshot(path=str(ROOT/'tests'/'artifacts'/'startup.png'))
        expect(page.locator('#startup-loader')).to_have_count(0, timeout=5000)
        expect(page.locator('#application-shell')).not_to_have_attribute('aria-hidden', 'true')
        assert page.locator('.workspace').evaluate("el => getComputedStyle(el).transitionDuration") != '0s'
        page.click('#mysql-toggle')
        expect(page.locator('#settings-dialog')).to_be_visible()
        assert 'dialogIn' in page.locator('#settings-dialog').evaluate("el => getComputedStyle(el).animationName")
        page.locator('#settings-dialog [data-close]').first.click()
        expect(page.locator('#settings-dialog')).to_have_class(re.compile(r'\bis-closing\b'))
        expect(page.locator('#settings-dialog')).to_be_hidden(timeout=1500)
        page.click('#advanced > summary')
        expect(page.locator('#advanced')).to_have_attribute('open', '')
        assert page.locator('#advanced').evaluate("el => el.getAnimations().some(animation => animation.playState === 'running')")
        expect(page.locator('#advanced')).not_to_have_class(re.compile(r'\bis-resizing\b'), timeout=1500)
        page.click('#advanced > summary')
        expect(page.locator('#advanced')).not_to_have_attribute('open', '', timeout=1500)
        assert not errors, errors
    finally:
        page.close()

    # Chybějící heslo nesmí preloader zablokovat; aplikace nabídne nastavení.
    page = browser.new_page(reduced_motion='reduce')
    page.add_init_script("""window.events=[]; window.pywebview={api:{
bootstrap:async()=>({ok:true,categories:['Tiefbau'],folder:'test-results',settings:{has_password:false}}),
folder_info:async()=>({ok:true,resume:false}),
poll_events:async()=>[], settings_password:async()=>({ok:true,password:''}),
save_categories:async(c)=>({ok:true,categories:c})
}};""")
    try:
        page.goto(url)
        expect(page.locator('#startup-loader')).to_have_count(0, timeout=3000)
        expect(page.locator('#settings-dialog')).to_be_visible()
        expect(page.locator('#application-shell')).not_to_have_attribute('aria-hidden', 'true')
    finally:
        page.close()

    # Ani chyba prvního MySQL připojení nebrání lokální práci v aplikaci.
    page = browser.new_page(reduced_motion='reduce')
    page.add_init_script("""window.events=[]; window.pywebview={api:{
bootstrap:async()=>({ok:true,categories:['Tiefbau'],folder:'test-results',settings:{has_password:true}}),
folder_info:async()=>({ok:true,resume:false}),
poll_events:async()=>window.events.splice(0,50),
connect_database:async()=>{window.events.push({type:'groups_error',message:'Testovací chyba MySQL'});return {ok:false}},
settings_password:async()=>({ok:true,password:'test-password'}),
save_categories:async(c)=>({ok:true,categories:c})
}};""")
    try:
        page.goto(url)
        expect(page.locator('#startup-loader')).to_have_count(0, timeout=3000)
        expect(page.locator('#application-shell')).not_to_have_attribute('aria-hidden', 'true')
        expect(page.locator('#notice-dialog')).to_be_visible()
        expect(page.locator('#notice-text')).to_contain_text('Testovací chyba MySQL')
    finally:
        page.close()

def main():
    server = ThreadingHTTPServer(('127.0.0.1',0),functools.partial(SimpleHTTPRequestHandler,directory=str(ROOT/'ui')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    previews = ROOT/'tests'/'artifacts'
    previews.mkdir(exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[1] if len(sys.argv)>1 else None,
                args=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage'])
            page=browser.new_page(viewport={'width':1320,'height':850},reduced_motion='reduce')
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.add_init_script(MOCK)
            page.goto(f'http://127.0.0.1:{server.server_port}')
            expect(page.locator('#start')).to_be_enabled()
            expect(page.locator('.main-rail .rail-button')).to_have_count(1)
            expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'true')
            expect(page.locator('.product-heading .brand-logo')).to_be_visible()
            page.click('#sidebar-toggle')
            expect(page.locator('#application-shell')).to_have_class(re.compile(r'\bsettings-collapsed\b'))
            expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'false')
            expect(page.locator('#sidebar-panel')).to_be_hidden()
            page.click('#sidebar-toggle')
            expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'true')
            expect(page.locator('#sidebar-panel')).to_be_visible()
            expect(page.locator('#portal')).to_have_value('wlw')
            assert page.locator('#browser-field').evaluate("el => getComputedStyle(el).transitionDuration") != '0s'
            page.select_option('#portal', '11880')
            expect(page.locator('#portal-help')).to_contain_text('přímo z profilů')
            page.screenshot(path=str(previews/'portal-11880.png'))
            expect(page.locator('#destination')).to_have_value('mysql')
            expect(page.locator('#skip-existing')).to_be_checked()
            expect(page.locator('#db-dot')).to_have_class('status-dot connected')
            page.click('#mysql-toggle')
            expect(page.locator('#db-password')).to_have_value('test-password')
            page.click('#password-toggle')
            expect(page.locator('#db-password')).to_have_attribute('type', 'text')
            expect(page.locator('#password-toggle')).to_have_attribute('aria-pressed', 'true')
            page.click('[data-close="settings-dialog"] >> text=Zrušit')
            expect(page.locator('#db-password')).to_have_value('')
            expect(page.locator('#db-password')).to_have_attribute('type', 'password')
            page.click('#category-summary')
            page.get_by_role('checkbox', name='Tiefbau', exact=True).uncheck()
            page.get_by_role('checkbox', name='Abbruch', exact=True).uncheck()
            expect(page.locator('#start')).to_be_disabled()
            page.click('#select-all-categories')
            expect(page.locator('#start')).to_be_enabled()
            page.fill('#new-category', 'Stahlbau')
            page.click('#add-category')
            expect(page.get_by_role('checkbox', name='Stahlbau', exact=True)).to_be_checked()
            page.get_by_role('button', name='Smazat kategorii Stahlbau', exact=True).click()
            expect(page.get_by_role('checkbox', name='Stahlbau', exact=True)).to_have_count(0)
            page.get_by_role('button', name='Smazat kategorii Tiefbau', exact=True).click()
            page.get_by_role('button', name='Smazat kategorii Abbruch', exact=True).click()
            expect(page.locator('#start')).to_be_disabled()
            expect(page.locator('#category input')).to_have_count(0)
            for name in ['Tiefbau', 'Abbruch']:
                page.fill('#new-category', name)
                page.click('#add-category')
                expect(page.get_by_role('checkbox', name=name, exact=True)).to_be_checked()
            page.screenshot(path=str(previews/'categories.png'))
            page.click('#category-summary')
            expect(page.locator('#group-field')).to_be_visible()
            expect(page.locator('#connect')).to_be_visible()
            page.select_option('#destination','files')
            page.click('label[for="skip-existing"]')
            expect(page.locator('#connect')).to_be_hidden()
            page.click('label[for="skip-existing"]')
            expect(page.locator('#connect')).to_be_visible()
            page.select_option('#destination','mysql')
            page.select_option('#portal', '11880')
            expect(page.locator('#portal-help')).to_contain_text('přímo z profilů')
            page.click('#start')
            expect(page.locator('#stop')).to_be_visible()
            expect(page.locator('#portal')).to_be_disabled()
            assert page.evaluate('window.lastConfig.portal') == '11880'
            expect(page.locator('#category input').first).to_be_disabled()
            assert page.evaluate('window.lastConfig.categories') == ['Tiefbau', 'Abbruch']
            assert page.evaluate('window.lastConfig.portal') == '11880'
            assert page.evaluate('window.lastConfig.output_mode') == 'mysql'
            assert page.evaluate('window.lastConfig.skip_existing') is True
            page.evaluate("""()=>{for(let i=0;i<80;i++){const status=i===0?'SKIPPED_EXISTING':i===1?'REVIEW':i===2?'ERROR':'OK';const data={status,origins:[{category:'Tiefbau',page:3},{category:'Abbruch',page:7}]};if(status==='OK')data.email='info@firma-'+i+'.example';if(status==='SKIPPED_EXISTING')data.skipped_existing=['known@firma.example'];events.push({type:'result',stage:4,url:'https://firma-'+i+'.example',data})}}""")
            expect(page.locator('#results-body tr')).to_have_count(80)
            page.select_option('#result-filter', 'emails')
            expect(page.locator('#results-body tr')).to_have_count(77)
            page.select_option('#result-filter', 'skipped')
            expect(page.locator('#results-body tr')).to_have_count(1)
            page.select_option('#result-filter', 'review')
            expect(page.locator('#results-body tr')).to_have_count(1)
            page.select_option('#result-filter', 'errors')
            expect(page.locator('#results-body tr')).to_have_count(1)
            page.select_option('#result-filter', 'all')
            expect(page.locator('#results-body tr')).to_have_count(80)
            page.fill('#search', 'Abbruch')
            expect(page.locator('#results-body tr')).to_have_count(80)
            expect(page.locator('#search-clear')).to_be_visible()
            page.click('#search-clear')
            expect(page.locator('#search')).to_be_focused()
            expect(page.locator('#results-body tr')).to_have_count(80)
            page.fill('#search', 'Neexistující kategorie')
            expect(page.locator('#results-body tr')).to_have_count(0)
            page.fill('#search', '')
            for width,height in [(1320,850),(1366,768),(1000,650),(900,560)]:
                page.set_viewport_size({'width':width,'height':height})
                for manual in [False,True]:
                    page.evaluate('(active)=>events.push({type:"manual",active})',manual)
                    expect(page.locator('#verification')).to_be_visible() if manual else expect(page.locator('#verification')).to_be_hidden()
                    page.wait_for_function("""() => {
                        const box = document.getElementById('table-scroll').getBoundingClientRect();
                        return box.height > 90 && box.bottom <= innerHeight;
                    }""")
                    box=page.locator('#table-scroll').bounding_box()
                    assert box['height']>90 and box['y']+box['height']<=height,box
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(previews/f'layout-{width}x{height}.png'))
            page.set_viewport_size({'width':1320,'height':850})
            page.evaluate('events.push({type:"manual",active:false})')
            expect(page.locator('#verification')).to_be_hidden()
            page.screenshot(path=str(previews/'light.png'))
            page.click('#theme-toggle')
            expect(page.locator('html')).to_have_attribute('data-theme','dark')
            page.screenshot(path=str(previews/'dark.png'))
            page.fill('#search','firma-12.')
            expect(page.locator('#results-body tr')).to_have_count(1)
            page.click('#results-body tr')
            expect(page.locator('#detail-dialog')).to_be_visible()
            expect(page.locator('#results-body tr td').nth(2)).to_have_text('Tiefbau, Abbruch')
            expect(page.locator('#detail-content')).to_contain_text('Tiefbau · stránka 3; Abbruch · stránka 7')
            page.screenshot(path=str(previews/'category-detail.png'))
            page.click('[data-close="detail-dialog"] >> text=Hotovo')
            page.click('#log-tab')
            expect(page.locator('#log-panel')).to_be_visible()
            expect(page.locator('#log-panel')).to_contain_text('11880.com · Tiefbau, Abbruch')
            page.evaluate("events.push({type:'log',message:'https://firma.example/ → OK [Kategorie: Tiefbau · stránka 3]'})")
            expect(page.locator('#log-panel')).to_contain_text('Kategorie: Tiefbau · stránka 3')
            page.click('#stop')
            expect(page.locator('#resume-run')).to_be_visible()
            expect(page.locator('#finish-run')).to_be_visible()
            expect(page.locator('#discard-run')).to_be_visible()
            page.click('#finish-run')
            expect(page.locator('#prepare-new')).to_be_visible()
            expect(page.locator('#prepare-new')).to_be_disabled()
            expect(page.locator('#stop')).to_be_hidden()
            page.evaluate("events.push({type:'idle'})")
            expect(page.locator('#prepare-new')).to_be_enabled()
            assert page.evaluate('window.lastFinishConfig.categories') == ['Tiefbau', 'Abbruch']
            page.click('#prepare-new')
            expect(page.locator('#start')).to_be_visible()
            expect(page.locator('#stat-emails')).to_have_text('0')
            expect(page.locator('#log-panel')).to_have_text('')
            expect(page.locator('#folder')).to_have_value('new-test-results')

            page.click('#start')
            page.click('#stop')
            expect(page.locator('#discard-run')).to_be_visible()
            page.click('#discard-run')
            expect(page.locator('#confirm-dialog')).to_be_visible()
            expect(page.locator('#confirm-cancel')).to_be_focused()
            page.click('#confirm-accept')
            expect(page.locator('#prepare-new')).to_be_visible()
            assert not errors,errors
            print('PASS: category column, category search, detail page numbers and responsive layouts', flush=True)
            startup_loader_smoke(browser, f'http://127.0.0.1:{server.server_port}/')
            portal_navigation_smoke(browser)
            delayed_bridge_smoke(browser, f'http://127.0.0.1:{server.server_port}/')
            browser.close()
            print('PASS: layouts plus start, stop, resume options, use data, discard and prepare-new controls')
    finally:
        server.shutdown()

if __name__=='__main__':
    main()
