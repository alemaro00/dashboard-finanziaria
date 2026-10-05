#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>

@interface DashboardAppDelegate : NSObject <NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, NSWindowDelegate>
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) WKWebView *webView;
@property(nonatomic, strong) NSTask *bridgeTask;
@property(nonatomic) BOOL ownsBridge;
@property(nonatomic) BOOL terminationPending;
@property(nonatomic) BOOL switchingBroker;
@property(nonatomic, copy) NSString *brokerMode;
@end

@implementation DashboardAppDelegate

static NSString *const DashboardURL = @"http://127.0.0.1:8767";

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    self.brokerMode = @"offline";
    NSMenu *menuBar = [[NSMenu alloc] init];
    NSMenuItem *appItem = [[NSMenuItem alloc] init];
    [menuBar addItem:appItem];
    NSMenu *menu = [[NSMenu alloc] initWithTitle:@"Beta Dashboard Finanziaria"];
    [menu addItemWithTitle:@"Informazioni su Beta Dashboard Finanziaria" action:@selector(orderFrontStandardAboutPanel:) keyEquivalent:@""];
    [menu addItem:NSMenuItem.separatorItem];
    NSMenuItem *connect = [menu addItemWithTitle:@"Collega TWS — sola lettura" action:@selector(connectReadOnly:) keyEquivalent:@""];
    connect.target = self;
    NSMenuItem *paperConnect = [menu addItemWithTitle:@"Collega TWS paper — sola lettura" action:@selector(connectPaperReadOnly:) keyEquivalent:@""];
    paperConnect.target = self;
    NSMenuItem *disconnect = [menu addItemWithTitle:@"Disconnetti TWS — modalità offline" action:@selector(disconnectBroker:) keyEquivalent:@""];
    disconnect.target = self;
    [menu addItem:NSMenuItem.separatorItem];
    [menu addItemWithTitle:@"Esci da Beta Dashboard Finanziaria" action:@selector(terminate:) keyEquivalent:@"q"];
    appItem.submenu = menu;

    NSMenuItem *editItem = [[NSMenuItem alloc] init];
    [menuBar addItem:editItem];
    NSMenu *editMenu = [[NSMenu alloc] initWithTitle:@"Modifica"];
    [editMenu addItemWithTitle:@"Annulla" action:@selector(undo:) keyEquivalent:@"z"];
    [editMenu addItem:NSMenuItem.separatorItem];
    [editMenu addItemWithTitle:@"Taglia" action:@selector(cut:) keyEquivalent:@"x"];
    [editMenu addItemWithTitle:@"Copia" action:@selector(copy:) keyEquivalent:@"c"];
    [editMenu addItemWithTitle:@"Incolla" action:@selector(paste:) keyEquivalent:@"v"];
    [editMenu addItemWithTitle:@"Seleziona tutto" action:@selector(selectAll:) keyEquivalent:@"a"];
    editItem.submenu = editMenu;
    NSApp.mainMenu = menuBar;
    NSURL *iconURL = [NSBundle.mainBundle URLForResource:@"AppIcon" withExtension:@"icns"];
    NSImage *appIcon = [[NSImage alloc] initWithContentsOfURL:iconURL];
    if (appIcon) [NSApp setApplicationIconImage:appIcon];

    WKWebViewConfiguration *configuration = [[WKWebViewConfiguration alloc] init];
    configuration.websiteDataStore = WKWebsiteDataStore.defaultDataStore;
    self.webView = [[WKWebView alloc] initWithFrame:NSZeroRect configuration:configuration];
    self.webView.navigationDelegate = self;
    self.webView.UIDelegate = self;

    self.window = [[NSWindow alloc]
        initWithContentRect:NSMakeRect(0, 0, 1380, 900)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
        backing:NSBackingStoreBuffered
        defer:NO];
    self.window.title = @"Beta Dashboard Finanziaria";
    self.window.delegate = self;
    self.webView.frame = self.window.contentView.bounds;
    self.webView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    self.window.contentView = self.webView;
    [self.window center];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
    [self openDashboard];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    return YES;
}

- (BOOL)windowShouldClose:(NSWindow *)sender {
    [NSApp terminate:nil];
    return NO;
}

- (void)connectReadOnly:(id)sender { [self changeBrokerMode:@"monitor-readonly"]; }
- (void)connectPaperReadOnly:(id)sender { [self changeBrokerMode:@"paper-readonly"]; }
- (void)disconnectBroker:(id)sender { [self changeBrokerMode:@"offline"]; }

- (void)changeBrokerMode:(NSString *)mode {
    if ([mode isEqualToString:self.brokerMode]) return;
    if (!self.ownsBridge || !self.bridgeTask.running || self.terminationPending || self.switchingBroker) {
        [self showError:@"Il servizio locale non è gestito da questa finestra. Chiudi le altre copie della dashboard e riapri l'app."];
        return;
    }
    self.switchingBroker = YES;
    __weak typeof(self) weakSelf = self;
    [self.webView callAsyncJavaScript:@"return window.dashboardFlushState ? await window.dashboardFlushState() : false;"
                           arguments:@{} inFrame:nil inContentWorld:WKContentWorld.pageWorld
                   completionHandler:^(id result, NSError *error) {
        if (error || ![result boolValue]) {
            weakSelf.switchingBroker = NO;
            [weakSelf showError:@"Salvataggio non confermato. La connessione resta invariata."];
            return;
        }
        weakSelf.brokerMode = mode;
        weakSelf.bridgeTask.terminationHandler = ^(NSTask *task) {
            dispatch_async(dispatch_get_main_queue(), ^{
                weakSelf.switchingBroker = NO;
                [weakSelf startBridge];
            });
        };
        [weakSelf stopOwnedBridge];
    }];
}

- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    if (self.switchingBroker) return NSTerminateCancel;
    if (self.terminationPending) return NSTerminateLater;
    self.terminationPending = YES;
    __weak typeof(self) weakSelf = self;
    [self.webView callAsyncJavaScript:@"return window.dashboardFlushState ? await window.dashboardFlushState() : true;"
                           arguments:@{} inFrame:nil inContentWorld:WKContentWorld.pageWorld
                   completionHandler:^(id result, NSError *error) {
        if (error || ![result boolValue]) {
            weakSelf.terminationPending = NO;
            [NSApp replyToApplicationShouldTerminate:NO];
            [weakSelf showError:@"Il salvataggio non è stato confermato. L'app resta aperta: verifica il servizio locale e riprova a chiudere."];
        } else {
            [weakSelf stopOwnedBridge];
            [NSApp replyToApplicationShouldTerminate:YES];
        }
    }];
    return NSTerminateLater;
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    [self stopOwnedBridge];
}

- (void)openDashboard {
    __weak typeof(self) weakSelf = self;
    [self checkBridge:^(BOOL available) {
        if (available) [weakSelf loadDashboard];
        else [weakSelf startBridge];
    }];
}

- (void)checkBridge:(void (^)(BOOL available))completion {
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:[DashboardURL stringByAppendingString:@"/api/health"]]];
    request.timeoutInterval = 0.8;
    [[[NSURLSession sharedSession] dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        NSDictionary *health = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        BOOL available = [(NSHTTPURLResponse *)response statusCode] == 200 && [health isKindOfClass:NSDictionary.class] && [health[@"service"] isEqual:@"ibkr-dashboard-bridge"] && [health[@"edition"] isEqual:@"beta-secure-storage-v1"] && [health[@"readOnlyBridge"] boolValue];
        dispatch_async(dispatch_get_main_queue(), ^{ completion(available); });
    }] resume];
}

- (void)startBridge {
    NSURL *runtime = [NSBundle.mainBundle.resourceURL URLByAppendingPathComponent:@"runtime" isDirectory:YES];
    NSURL *python = [runtime URLByAppendingPathComponent:@"bridge/dashboard-bridge"];
    NSURL *bridge = python;
    if (![NSFileManager.defaultManager isExecutableFileAtPath:python.path]) {
        [self showError:@"Runtime incorporato non disponibile: reinstalla la beta."];
        return;
    }
    if (![NSFileManager.defaultManager fileExistsAtPath:bridge.path]) {
        [self showError:@"Risorse interne della dashboard non disponibili."];
        return;
    }
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = python;
    task.arguments = @[@"--no-browser", @"--broker-mode", self.brokerMode, @"--http-port", @"8767"];
    task.currentDirectoryURL = runtime;
    NSURL *logDirectory = [NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory inDomains:NSUserDomainMask].firstObject;
    logDirectory = [logDirectory URLByAppendingPathComponent:@"Dashboard Finanziaria Beta" isDirectory:YES];
    [NSFileManager.defaultManager createDirectoryAtURL:logDirectory withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions: @0700} error:nil];
    NSURL *logURL = [logDirectory URLByAppendingPathComponent:@"bridge.log"];
    [NSFileManager.defaultManager createFileAtPath:logURL.path contents:nil attributes:@{NSFilePosixPermissions: @0600}];
    NSFileHandle *logHandle = [NSFileHandle fileHandleForWritingToURL:logURL error:nil];
    task.standardOutput = logHandle;
    task.standardError = logHandle;
    NSMutableDictionary *environment = [@{@"PATH": @"/usr/bin:/bin", @"HOME": NSHomeDirectory(), @"TMPDIR": NSTemporaryDirectory(), @"LANG": @"it_IT.UTF-8"} mutableCopy];
    environment[@"DASHBOARD_DATA_DIR"] = logDirectory.path;
    environment[@"DASHBOARD_RESOURCE_DIR"] = runtime.path;
    environment[@"DASHBOARD_KEYCHAIN_HELPER"] = [[NSBundle.mainBundle.executableURL URLByDeletingLastPathComponent] URLByAppendingPathComponent:@"DashboardKeychain"].path;
    environment[@"DASHBOARD_REQUIRE_ENCRYPTION"] = @"1";
    task.environment = environment;
    NSError *error = nil;
    if (![task launchAndReturnError:&error]) {
        [self showError:[NSString stringWithFormat:@"Impossibile avviare il servizio locale: %@", error.localizedDescription]];
        return;
    }
    self.bridgeTask = task;
    self.ownsBridge = YES;
    [self waitForBridge:0];
}

- (void)waitForBridge:(NSInteger)attempt {
    if (attempt >= 60) {
        [self showError:@"Il servizio locale non ha risposto entro il tempo previsto."];
        return;
    }
    __weak typeof(self) weakSelf = self;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.25 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        [weakSelf checkBridge:^(BOOL available) {
            if (available) [weakSelf loadDashboard];
            else [weakSelf waitForBridge:attempt + 1];
        }];
    });
}

- (void)loadDashboard {
    NSURLRequest *request = [NSURLRequest requestWithURL:[NSURL URLWithString:[DashboardURL stringByAppendingString:@"/"]] cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:15];
    [self.webView loadRequest:request];
}

- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    if (error.code != NSURLErrorCancelled) [self showError:@"Impossibile caricare la Dashboard locale. Chiudi e riapri la beta; i dati salvati non vengono eliminati."];
}

- (void)webViewWebContentProcessDidTerminate:(WKWebView *)webView {
    [self showError:@"Il contenuto della finestra si è interrotto. Riapri la beta per recuperare i dati già salvati."];
}

- (void)webView:(WKWebView *)webView decidePolicyForNavigationAction:(WKNavigationAction *)navigationAction decisionHandler:(void (^)(WKNavigationActionPolicy))decisionHandler {
    NSURL *url = navigationAction.request.URL;
    if (navigationAction.shouldPerformDownload && [url.scheme isEqualToString:@"blob"]) {
        decisionHandler(WKNavigationActionPolicyDownload);
        return;
    }
    NSString *host = url.host.lowercaseString;
    BOOL isLocal = ([host isEqualToString:@"127.0.0.1"] || [host isEqualToString:@"localhost"]) && [url.scheme isEqualToString:@"http"] && url.port.integerValue == 8767;
    if (url && !isLocal && ([url.scheme isEqualToString:@"https"] || [url.scheme isEqualToString:@"http"])) {
        [NSWorkspace.sharedWorkspace openURL:url];
        decisionHandler(WKNavigationActionPolicyCancel);
        return;
    }
    decisionHandler(isLocal ? WKNavigationActionPolicyAllow : WKNavigationActionPolicyCancel);
}

- (void)stopOwnedBridge {
    if (self.ownsBridge && self.bridgeTask.running) [self.bridgeTask terminate];
    self.ownsBridge = NO;
}

- (WKWebView *)webView:(WKWebView *)webView createWebViewWithConfiguration:(WKWebViewConfiguration *)configuration forNavigationAction:(WKNavigationAction *)navigationAction windowFeatures:(WKWindowFeatures *)windowFeatures {
    NSURL *url = navigationAction.request.URL;
    BOOL local = [url.host isEqualToString:@"127.0.0.1"] && [url.scheme isEqualToString:@"http"] && url.port.integerValue == 8767;
    if ([url.scheme isEqualToString:@"https"] || local) [NSWorkspace.sharedWorkspace openURL:url];
    return nil;
}

- (void)webView:(WKWebView *)webView navigationAction:(WKNavigationAction *)navigationAction didBecomeDownload:(WKDownload *)download {
    download.delegate = self;
}

- (void)download:(WKDownload *)download decideDestinationUsingResponse:(NSURLResponse *)response suggestedFilename:(NSString *)suggestedFilename completionHandler:(void (^)(NSURL *))completionHandler {
    NSSavePanel *panel = [NSSavePanel savePanel];
    panel.nameFieldStringValue = @"dashboard-backup.dfbackup";
    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse result) {
        completionHandler(result == NSModalResponseOK ? panel.URL : nil);
    }];
}

- (void)showError:(NSString *)message {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Dashboard Finanziaria";
    alert.informativeText = message;
    alert.alertStyle = NSAlertStyleCritical;
    [alert runModal];
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *application = NSApplication.sharedApplication;
        DashboardAppDelegate *delegate = [[DashboardAppDelegate alloc] init];
        application.delegate = delegate;
        [application run];
    }
    return 0;
}
