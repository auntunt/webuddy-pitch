// Isolated demonstration only. Secrets are provided outside the repository.
import groovy.json.JsonSlurper
import jenkins.model.Jenkins
import hudson.security.HudsonPrivateSecurityRealm
import hudson.security.GlobalMatrixAuthorizationStrategy
import hudson.model.Item
import hudson.model.User
import jenkins.security.ApiTokenProperty
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey
import org.jenkinsci.plugins.gitclient.GitHostKeyVerificationConfiguration
import org.jenkinsci.plugins.gitclient.verifier.ManuallyProvidedKeyVerificationStrategy

def instance = Jenkins.get()
def folder = new File(instance.rootDir, 'secrets/webuddy-demo')
def marker = new File(folder, 'initialized')
if (!marker.exists()) {
    def accounts = new JsonSlurper().parse(new File(folder, 'accounts.json'))
    def realm = new HudsonPrivateSecurityRealm(false)
    realm.createAccount(accounts.admin_user, accounts.admin_password)
    realm.createAccount(accounts.reader_user, accounts.reader_password)
    instance.securityRealm = realm
    def auth = new GlobalMatrixAuthorizationStrategy()
    auth.add(Jenkins.ADMINISTER, accounts.admin_user)
    auth.add(Jenkins.READ, accounts.reader_user)
    auth.add(Item.READ, accounts.reader_user)
    instance.authorizationStrategy = auth
    instance.numExecutors = 1
    def token = User.getById(accounts.reader_user, true).getProperty(ApiTokenProperty).tokenStore.generateNewToken('webuddy-ci-read')
    def tokenFile = new File(folder, 'reader-token')
    tokenFile.text = token.plainValue
    tokenFile.setReadable(false, false); tokenFile.setReadable(true, true)
    tokenFile.setWritable(false, false); tokenFile.setWritable(true, true)
    User.getById(accounts.reader_user, true).save()
    def key = new BasicSSHUserPrivateKey(CredentialsScope.GLOBAL, 'demo-git', 'git',
        new BasicSSHUserPrivateKey.DirectEntryPrivateKeySource(new File(folder, 'git-client').text), '', 'Isolated ERP repository')
    SystemCredentialsProvider.getInstance().credentials.add(key)
    SystemCredentialsProvider.getInstance().save()
    GitHostKeyVerificationConfiguration.get().setSshHostKeyVerificationStrategy(
        new ManuallyProvidedKeyVerificationStrategy(new File(folder, 'known_hosts').text))
    instance.save()
    marker.text = 'isolated-demo-initialized\n'
}
