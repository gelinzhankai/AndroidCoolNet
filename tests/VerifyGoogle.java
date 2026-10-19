import com.android.apksig.ApkVerifier;
import java.io.File;
import java.security.MessageDigest;
import java.util.HexFormat;

// Development-time signature verification. Runtime accepts only the resulting SHA-256 pins.
class VerifyGoogle {
    public static void main(String[] args) throws Exception {
        var result = new ApkVerifier.Builder(new File(args[0])).build().verify();
        if (!result.isVerified()) throw new SecurityException(result.getAllErrors().toString());
        var lineage = result.getSigningCertificateLineage();
        var certs = lineage == null ? result.getSignerCertificates() : lineage.getCertificatesInLineage();
        boolean trusted = false;
        for (var cert : certs) {
            String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(cert.getEncoded()));
            System.out.println(digest);
            trusted |= digest.equals("f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83");
        }
        if (!trusted) throw new SecurityException("Google certificate anchor missing");
    }
}
