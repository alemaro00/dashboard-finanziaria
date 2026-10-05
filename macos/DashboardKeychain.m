#import <Foundation/Foundation.h>
#import <Security/Security.h>
#include <unistd.h>

// Private pipe output only. Never put key material into arguments, files or logs.
int main(void) {
    @autoreleasepool {
        NSDictionary *query = @{
            (__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
            (__bridge id)kSecAttrService: @"it.alemaro.dashboard-finanziaria.beta.storage",
            (__bridge id)kSecAttrAccount: @"local-encryption-v1",
            (__bridge id)kSecAttrSynchronizable: @NO
        };
        NSMutableDictionary *lookup = query.mutableCopy;
        lookup[(__bridge id)kSecReturnData] = @YES;
        lookup[(__bridge id)kSecMatchLimit] = (__bridge id)kSecMatchLimitOne;
        CFTypeRef result = NULL;
        OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)lookup, &result);
        if (status == errSecItemNotFound) {
            unsigned char bytes[32];
            if (SecRandomCopyBytes(kSecRandomDefault, sizeof(bytes), bytes) != errSecSuccess) return 2;
            NSData *key = [NSData dataWithBytes:bytes length:sizeof(bytes)];
            NSMutableDictionary *create = query.mutableCopy;
            create[(__bridge id)kSecValueData] = key;
            create[(__bridge id)kSecAttrAccessible] = (__bridge id)kSecAttrAccessibleWhenUnlockedThisDeviceOnly;
            status = SecItemAdd((__bridge CFDictionaryRef)create, NULL);
            if (status == errSecSuccess) return write(STDOUT_FILENO, key.bytes, key.length) == 32 ? 0 : 3;
            if (status == errSecDuplicateItem) status = SecItemCopyMatching((__bridge CFDictionaryRef)lookup, &result);
        }
        if (status != errSecSuccess || result == NULL) return 4;
        NSData *key = CFBridgingRelease(result);
        if (key.length != 32) return 5;
        return write(STDOUT_FILENO, key.bytes, key.length) == 32 ? 0 : 6;
    }
}
