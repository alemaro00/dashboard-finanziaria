#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>

@interface DashboardAppDelegate : NSObject <NSApplicationDelegate, WKNavigationDelegate>
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) WKWebView *webView;
@property(nonatomic, strong) NSTask *bridgeTask;
@property(nonatomic) BOOL ownsBridge;
@property(nonatomic) BOOL terminationPending;
@end

@implementation DashboardAppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    NSURL *iconURL = [NSBundle.mainBundle URLForResource:@"AppIcon" withExtension:@"icns"];
    NSImage *appIcon = [[NSImage alloc] initWithContentsOfURL:iconURL];
    if (appIcon) [NSApp setApplicationIconImage:appIcon];

    WKWebViewConfiguration *configuration = [[WKWebViewConfiguration alloc] init];
    configuration.websiteDataStore = WKWebsiteDataStore.defaultDataStore;
    self.webView = [[WKWebView alloc] initWithFrame:NSZeroRect configuration:configuration];
    self.webView.navigationDelegate = self;

    self.window = [[NSWindow alloc]
        initWithContentRect:NSMakeRect(0, 0, 1380, 900)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
        backing:NSBackingStoreBuffered
        defer:NO];
    self.window.title = @"Dashboard Finanziaria";
    self.window.contentView = self.webView;
    [self.window center];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
    [self openDashboard];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    return YES;
}

- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    if (self.terminationPending) return NSTerminateNow;
    self.terminationPending = YES;
    __weak typeof(self) weakSelf = self;
    [self.webView evaluateJavaScript:@"window.dispatchEvent(new PageTransitionEvent('pagehide'))" completionHandler:^(id result, NSError *error) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.6 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
            [weakSelf stopOwnedBridge];
            [NSApp replyToApplicationShouldTerminate:YES];
        });
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
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:@"http://127.0.0.1:8765/api/health"]];
    request.timeoutInterval = 0.8;
    [[[NSURLSession sharedSession] dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        BOOL available = [(NSHTTPURLResponse *)response statusCode] == 200;
        dispatch_async(dispatch_get_main_queue(), ^{ completion(available); });
    }] resume];
}

- (void)startBridge {
    NSURL *runtime = [NSBundle.mainBundle.resourceURL URLByAppendingPathComponent:@"runtime" isDirectory:YES];
    NSURL *python = [NSURL fileURLWithPath:@"/usr/bin/python3"];
    NSURL *bridge = [runtime URLByAppendingPathComponent:@"ibkr_paper_bridge.py"];
    if (![NSFileManager.defaultManager isExecutableFileAtPath:python.path]) {
        [self showError:@"Python di sistema non disponibile."];
        return;
    }
    if (![NSFileManager.defaultManager fileExistsAtPath:bridge.path]) {
        [self showError:@"Risorse interne della dashboard non disponibili."];
        return;
    }
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = python;
    task.arguments = @[bridge.path, @"--no-browser"];
    task.currentDirectoryURL = runtime;
    NSURL *logDirectory = [NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory inDomains:NSUserDomainMask].firstObject;
    logDirectory = [logDirectory URLByAppendingPathComponent:@"Dashboard Finanziaria" isDirectory:YES];
    [NSFileManager.defaultManager createDirectoryAtURL:logDirectory withIntermediateDirectories:YES attributes:nil error:nil];
    NSURL *logURL = [logDirectory URLByAppendingPathComponent:@"bridge.log"];
    [NSFileManager.defaultManager createFileAtPath:logURL.path contents:nil attributes:nil];
    NSFileHandle *logHandle = [NSFileHandle fileHandleForWritingToURL:logURL error:nil];
    task.standardOutput = logHandle;
    task.standardError = logHandle;
    NSMutableDictionary *environment = NSProcessInfo.processInfo.environment.mutableCopy;
    environment[@"PYTHONPATH"] = [[runtime URLByAppendingPathComponent:@"python" isDirectory:YES] path];
    environment[@"PYTHONPYCACHEPREFIX"] = [[logDirectory URLByAppendingPathComponent:@"pycache" isDirectory:YES] path];
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
    NSURLRequest *request = [NSURLRequest requestWithURL:[NSURL URLWithString:@"http://127.0.0.1:8765/"] cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:15];
    [self.webView loadRequest:request];
}

- (void)stopOwnedBridge {
    if (self.ownsBridge && self.bridgeTask.running) [self.bridgeTask terminate];
    self.ownsBridge = NO;
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
