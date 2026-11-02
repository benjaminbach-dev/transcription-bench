# Sonde locale : aucune voix ni dépendance n'est téléchargée.
# Exécuter avec Windows PowerShell 5.1 (System.Speech / .NET Framework).
param([string]$Sortie = "data/ci/audio/parole.wav")
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$synthese = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voix = @($synthese.GetInstalledVoices() | Where-Object { $_.Enabled } |
        Sort-Object { $_.VoiceInfo.Culture.Name }, { $_.VoiceInfo.Name })
    if ($voix.Count -eq 0) {
        throw "Aucune voix systeme locale disponible. Arbitrage requis, aucun telechargement automatique."
    }
    $choisie = $voix | Where-Object {
        $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq "en"
    } | Select-Object -First 1
    if ($null -eq $choisie) {
        $choisie = $voix | Where-Object {
            $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq "fr"
        } | Select-Object -First 1
    }
    if ($null -eq $choisie) { $choisie = $voix[0] }
    $nom = $choisie.VoiceInfo.Name
    $culture = $choisie.VoiceInfo.Culture.Name
    $texteLangue = "en"
    $texte = "Hello. This is a short synthetic speech recording to test the transcription program. The data is artificial. This is a software test, not a model quality assessment."
    if ($choisie.VoiceInfo.Culture.TwoLetterISOLanguageName -eq "fr") {
        $texteLangue = "fr"
        $texte = "Bonjour. Ceci est une parole synthetique pour tester le fonctionnement du programme. Les donnees sont artificielles. Ce test logiciel ne mesure pas la qualite du modele."
    }
    $synthese.SelectVoice($nom)
    $chemin = [System.IO.Path]::GetFullPath($Sortie)
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($chemin)) | Out-Null
    $synthese.SetOutputToWaveFile($chemin)
    $synthese.Speak($texte)
    $synthese.SetOutputToNull()
    # Culture de la voix et langue du texte sont des observations distinctes.
    $preuve = @{ voix = $nom; culture_voix = $culture; texte_langue = $texteLangue;
        sha256 = (Get-FileHash $chemin -Algorithm SHA256).Hash.ToLowerInvariant() }
    $json = $preuve | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText([System.IO.Path]::ChangeExtension($chemin, ".json"),
        $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Output $json
} finally {
    $synthese.Dispose()
}
