Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = 1
$synth.Volume = 100
foreach ($v in $synth.GetInstalledVoices()) {
    if ($v.VoiceInfo.Name -match 'Zira|Hazel|Aria|Jenny|David') {
        $synth.SelectVoice($v.VoiceInfo.Name)
        break
    }
}
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s1_open.wav', $fmt)
$synth.Speak('A screening journey is only complete when care happens. This is CareBridge — closing the screening to care loop.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s1_journey.wav', $fmt)
$synth.Speak('The patient signs in to her empty fourteen-stage care pathway, where every stage completes only from persisted evidence.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s2_intake.wav', $fmt)
$synth.Speak('She speaks naturally with the role-aware AI assistant, which captures her screening need and creates a real task for the Care Coordinator.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s2_coord.wav', $fmt)
$synth.Speak('The Care Coordinator signs in. Watch the coordinator task and notification arrive — from a persisted database record, not from a chat promise.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s3_order.wav', $fmt)
$synth.Speak('The coordinator creates the screening order. Notice Stage One remains pending: an order alone is not proof that screening took place.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s3_performed.wav', $fmt)
$synth.Speak('Once the performed screening is recorded, Stage One turns green. Next, the coordinator uploads the actual synthetic PDF report.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s3_finalized.wav', $fmt)
$synth.Speak('Upload alone does not complete Stage Two. Only after the report is validated and finalized do Stage Two and Stage Three complete.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s4_notif.wav', $fmt)
$synth.Speak('The patient receives her result notification and asks what the finalized BI-RADS Four report means.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s4_explain.wav', $fmt)
$synth.Speak('The assistant retrieves the actual finalized report and explains it in clear, plain language without diagnosing.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s4_stage4.wav', $fmt)
$synth.Speak('Delivery of that persisted explanation is recorded as evidence to complete Stage Four.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s5_convo1.wav', $fmt)
$synth.Speak('In a natural follow-up conversation, the patient asks where she is in her care journey and what happens next with her doctor.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s5_convo2.wav', $fmt)
$synth.Speak('Using her authorized case context, the AI answers directly with one persisted response — never repeating or inventing clinical facts.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s6_ref_appt.wav', $fmt)
$synth.Speak('A specialist referral is created and accepted. Stage Nine turns green only after both doctor and patient confirm the exact same appointment version.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s6_doc_login.wav', $fmt)
$synth.Speak('Doctor Arjun Menon signs in, reviews the diagnostic findings, and records the clinical decision and biopsy consultation outcome.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s6_followup.wav', $fmt)
$synth.Speak('Stage Ten completes, and treatment monitoring, follow-up, and the ten-point documentation checklist advance from persisted records.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s7_boundary.wav', $fmt)
$synth.Speak('Now test the role boundary: the Care Coordinator attempts to close the case and is blocked.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s7_closure.wav', $fmt)
$synth.Speak('Only an authorized doctor can sign off clinical closure — completing fourteen of fourteen stages with full timeline events and referral evidence.')
$synth.SetOutputToWaveFile('C:\CareBridge\demo_assets\audio\cues\s8_close.wav', $fmt)
$synth.Speak('Patient, doctor, and care coordinator share one PostgreSQL-backed workflow. Synthetic data only. Team Ai Mavericks.')
$synth.SetOutputToNull()
$synth.Dispose()