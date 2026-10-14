package com.acme.oa.util;

import java.security.MessageDigest;

public class PasswordUtil {
    public static String hash(String raw) throws Exception {
        MessageDigest md = MessageDigest.getInstance("MD5");
        byte[] out = md.digest(raw.getBytes());
        return new String(out);
    }
}
