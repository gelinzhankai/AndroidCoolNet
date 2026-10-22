import com.android.apksig.ApkVerifier;
import java.io.File;
import java.security.MessageDigest;
import java.util.HexFormat;

// Maintainer-only: verify each split with Android's verifier and a reviewed signer anchor.
class VerifyAppSet {
    public static void main(String[] args) throws Exception {
        for (int i = 2; i < args.length; i++) {
            var result = new ApkVerifier.Builder(new File(args[i])).build().verify();
            if (!result.isVerified()) throw new SecurityException(result.getAllErrors().toString());
            var certificates = result.getSignerCertificates();
            if (certificates.size() != 1) throw new SecurityException("Unexpected signer count");
            byte[] cert = certificates.get(0).getEncoded();
            String anchor = HexFormat.of().formatHex(MessageDigest.getInstance(args[0]).digest(cert));
            if (!anchor.equals(args[1])) throw new SecurityException("Signer does not match reviewed source");
            System.out.println(new File(args[i]).getName() + " " +
                HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(cert)));
        }
    }
}
