// Extract the Find My data-manager keychain keys that decrypt the fmipcore
// cache. Works only with AMFI disabled (amfi_get_out_of_my_way=1) + an ad-hoc
// signature carrying the keychain-access-groups entitlement
// "0000000000.com.apple.findmy" (the platform-prefixed Find My group), so
// securityd honors the otherwise Apple-reserved group.
//
//   FMIPDataManager -> Items.data / Devices.data / FamilyMembers.data / …
//   FMFDataManager  -> FriendCacheData.data
//
// Query mirrors the reference extractor (generic password, by service name,
// no explicit access group, no data-protection flag). Prints base64 of each
// key blob (a bplist whose `symmetricKey` field is the 32-byte ChaCha key).
import Foundation
import Security

func extract(_ service: String) -> Data? {
    let q: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: service,
        kSecMatchLimit as String: kSecMatchLimitOne,
        kSecReturnData as String: true,
    ]
    var out: CFTypeRef?
    let st = SecItemCopyMatching(q as CFDictionary, &out)
    if st == errSecSuccess, let d = out as? Data { return d }
    FileHandle.standardError.write("  (service=\(service) status=\(st))\n".data(using: .utf8)!)
    return nil
}

for svc in ["FMIPDataManager", "FMFDataManager"] {
    if let d = extract(svc) {
        print("KEY service=\(svc) len=\(d.count) DATA_B64=\(d.base64EncodedString())")
    } else {
        print("KEY service=\(svc) MISSING")
    }
}
