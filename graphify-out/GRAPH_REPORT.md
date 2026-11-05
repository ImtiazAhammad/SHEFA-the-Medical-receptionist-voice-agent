# Graph Report - Voice_agent  (2026-11-05)

## Corpus Check
- 203 files · ~182,658 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 12 file(s) not represented in the graph (top: (none) 3, .tmpl 3, .css 2)

## Summary
- 4166 nodes · 8739 edges · 240 communities (179 shown, 61 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 1134 edges (avg confidence: 0.89)
- Token cost: 848,503 input · 0 output

## Community Hubs (Navigation)
- Call Session Management
- FastAPI App and Calls
- Coverage Policy Gate
- LLM Adapters
- React Owner Console
- Spoken Dates and Actions
- Config Loading Tests
- Settings Config Models
- Media Queue Concurrency
- Reminders and Browser Calls
- AudioSocket Call Simulation
- Asterisk Call Leg
- OpenAI-Compatible LLM Tests
- Shefa CLI Commands
- STT Adapters
- Failure Taxonomy Harness
- Lab Dates and Scenarios
- Twilio Media and Call Log
- Auth Token Store
- Lab Scenario Runner
- Default Pipeline Config
- Voice Pipeline Streaming
- Calls Store
- Audio Codec Boundary
- Append-Only Audit Table
- Whisper Confidence Scoring
- Model Bench Script
- Telephony Provider Health
- Model Registry and TTS
- Base Model Contracts
- Piper TTS Adapter
- Reminder Cycle Tests
- Audio Frame Streaming
- Clinic Directory Import
- Audit Store
- Mulaw Audio Conversion
- STT Confidence Tests
- Twilio Inbound Decoding
- TTS Persistent Session
- PHI Compliance Utilities
- Bench Evaluation
- Whisper Local Loading
- Booking Confirmation Text
- Emergency Detection Corpus
- Speak-To Playback Tests
- VRAM Measurement
- Asterisk Telephony Plan
- Pipeline Language Detection
- PHI Access Authorization
- Other-Language Routing Tests
- Model Adapter Config
- Open-Weight LLM Research
- Lead Sink and Dashboard
- Failure Taxonomy
- Voice Model Fetching
- Clinic Store Core
- Model Warmup Tests
- API Error Envelope
- Appointment Booking Tests
- Call Control Legs
- Fake Piper Voices
- Telephony Router Gating
- CI Workflow
- LLM Pull Status
- Kokoro Local Voice
- Action Argument Resolution
- Energy VAD
- Structured Logging and Masking
- Text Chat Tests
- Owner Console Plan
- Language Detector Tests
- Tool Executor
- Twilio Stream Addressing
- Escalation Config
- Console App TS Config
- First-Clinic Epic
- Bangla ASR Research
- Console API Tests
- Voice Flow Tests
- Lab Report Rendering
- Twilio Webhook Tests
- Clinic EHR Integration
- Language-Routed STT
- Whisper Transcribe Fallback
- Authorized API Access
- Telephony Config
- Appointment Status Store
- Language-Routed TTS
- CLI Bench Tests
- VAD Audio Processing
- Console Node TS Config
- Demo and Fine-Tuning Guides
- Local Telephony Child Epic
- Voice Registry Config
- Lab Execution
- Voice Fetch Tests
- Action Parsing Tests
- API Endpoint Tests
- Browser Login Auth
- TTS Failure Voices
- Token Verification
- App and Session Config
- Bangla Datasets and Licences
- Asterisk Config Rendering
- Pipeline Reply Generation
- Standalone Pipeline Script
- Calendar Integration
- Model Fetch Checks
- VITS Voice Fetching
- Twilio Helper Coverage
- Clinic Example Config
- Demo Deliverable Gates
- Developer Loop Child Epic
- VAD Fixture Tests
- README Operations Roadmap
- Test Call Page
- Bench Subprocess Runner
- Startup Model Warmup
- Hosted Provider Tests
- Action Extraction Tests
- Call Dial Routing Tests
- Media Stream Cancellation
- Active Call Tracking
- Receptionist System Prompt
- Config Merge and Env
- Telephony Config Tests
- Twilio Leg Tests
- VITS TTS Adapter
- Whisper Bilingual Tests
- Clinic Integration Tests
- Lab Turn Checks
- Speech Model Fetch
- Threaded TTS Wrapper
- Twilio Call Leg
- CLI Bench Command Tests
- CLI Doctor Tests
- CLI Token Tests
- Scripted Voice Calls
- Text Chat and Console Docs
- Free Demo Providers
- Safety-Net Child Epic
- Queue Bounds Brief
- Project Memory Brief
- Bench Measure Tests
- UTC Day Boundary
- API Status Code Tests
- CLI Argument Parsing
- LLM Base Tests
- TTS Barge-In Tests
- Fake WebSocket Media Tests
- LLM Adapter Resolution
- Integrations Config
- Monitoring Config
- Safety-Net Wedge Approaches
- Owner Console Page
- Percentile Tests
- Legacy Dashboard Sessions
- Tool Transfer Tests
- Route Auth Coverage
- Outbound Reminder Pipeline
- Local TTS Research
- CLI Doctor Speech Tests
- Lab CLI Tests
- Fetch-All Tests
- Model Fetch Module
- Latency Ceiling Decisions
- Runbook Child Epic
- OpenAI LLM Tests
- Router Bench Script
- Principal Authorization
- Sentence Splitting
- Legacy Dashboard Views
- Media Queue Stall Tests
- Test Isolation Fixtures
- API Auth Shared Store
- Unconfigured Auth Lockdown
- Nvidia-SMI Parsing
- Clinic Loader Tests
- OpenAI STT Confidence
- Piper Stream Pump
- Auth Config
- Compliance Config
- Notification Config
- Console Icon Sprite
- STT Model Fetch Script
- Twilio Config Tests
- Error Text Tests
- Setup Demo Tests
- Database Backup Script
- Language Greeting Config
- Asterisk Docker Compose
- Disclosure Approval Gate
- Lab Voice Test Page
- Patient Records Store
- Lab Transcript Measures
- Logging Config Wiring
- Media Queue Decision Tests
- Twilio Stub Client
- Clinic Fixture Tests
- Turn Timing Tests
- English Whisper Config
- Local Whisper Config
- Oxlint Config
- Multi-Branch Build Order
- TTS Adapter Defaults
- Asterisk Fake Pipeline
- Emergency Transfer Test
- Lab Scripted Model
- Playback Resample Test
- Playback Empty Result Test
- Playback Encoding Test
- Playback Dead Socket Test
- Playback Exception Test
- VAD Fixture Pipeline Test
- Local LLM Config
- Monitoring Config Tests
- Pipeline Helper Regression
- Piper Registry Wiring
- Outbound Encode Tests
- Inbound Media Enqueue Test
- Coverage Ratchet Policy
- Tool Result Notes
- Registry Adapter Tests
- Media Stream Stop Test
- VAD Recording Sink
- Root TS Config
- Bench Report
- Language Enum
- LLM Tool Flag Config
- SIP Trunk Config
- WAV Data Chunk Test
- Agent Routing Rules
- Console Favicon
- Vite Logo
- Hero Illustration
- React Logo
- Package Root

## God Nodes (most connected - your core abstractions)
1. `AudioFrame` - 122 edges
2. `Language` - 94 edges
3. `CallSession` - 62 edges
4. `default_clinic_store()` - 56 edges
5. `ClinicStore` - 56 edges
6. `VoicePipeline` - 56 edges
7. `create_app()` - 51 edges
8. `StrictModel` - 47 edges
9. `PiperTTS` - 47 edges
10. `WhisperLocalSTT` - 40 edges

## Surprising Connections (you probably didn't know these)
- `synthesize_stream()` --calls--> `AudioFrame`  [INFERRED]
  tests/unit/test_reminders.py → src/shefa/audio.py
- `test_cli_import_failures_exit_nonzero()` --calls--> `main()`  [INFERRED]
  tests/unit/test_clinic_loader.py → src/shefa/cli.py
- `test_the_phone_number_identifies_the_patient_on_the_first_message()` --calls--> `default_clinic_store()`  [INFERRED]
  tests/unit/test_text_chat.py → src/shefa/clinic/default.py
- `test_the_registry_builds_azure_voices()` --uses--> `VoiceConfig`  [INFERRED]
  tests/unit/test_hosted_providers.py → src/shefa/config/settings.py
- `test_cuda_is_selected_when_torch_reports_it()` --uses--> `WhisperLocalSTT`  [INFERRED]
  tests/unit/test_whisper_local.py → src/shefa/models/stt/whisper_local.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Typed turn through the voice pipeline's logic** — src_shefa_static_console_sendtext, src_shefa_static_test_call_textsend, readme_typed_chat_endpoint, readme_voice_pipeline [INFERRED 0.85]
- **Emergency handoff to a human** — configs_prompts_system_emergency_handoff_rule, readme_emergency_detection, src_shefa_static_console_sendtext, todos_demo_safety_signoff [INFERRED 0.75]
- **Twilio to self-hosted Asterisk migration** — readme_asterisk_pbx_integration, readme_sip_trunk, readme_twilio_development_sink, todos_pa3_twilio_full_removal, todos_d7_freeswitch_esl_adapter, memory_twilio_media_streams_architecture [INFERRED 0.85]
- **SHEFA Epic Child Decomposition** — docs_designs_shefa_spec_epic_plan_child_0_developer_loop, docs_designs_shefa_spec_epic_plan_child_1_media_path, docs_designs_shefa_spec_epic_plan_child_2_conversation, docs_designs_shefa_spec_epic_plan_child_3_lead_sink_dashboard, docs_designs_shefa_spec_epic_plan_child_4_real_loop_test, docs_designs_shefa_spec_epic_plan_child_5_runbook_docs, docs_designs_shefa_spec_epic_plan_child_6_demo, docs_designs_shefa_spec_epic_plan_child_7_booking_hms, docs_designs_shefa_spec_epic_plan_child_8_fleet [EXTRACTED 1.00]
- **SHEFA Media and Call-Control Plane** — docs_designs_shefa_spec_epic_plan_media_bridge, docs_designs_shefa_spec_epic_plan_asterisk_ari_adapter, docs_designs_shefa_spec_epic_plan_freeswitch_esl_adapter, docs_designs_shefa_spec_epic_plan_call_control, docs_designs_shefa_spec_epic_plan_call_leg, docs_designs_shefa_spec_epic_plan_audio_frame [EXTRACTED 1.00]
- **SHEFA Emergency Safety Path** — docs_designs_shefa_spec_epic_plan_intent_router_emergency, docs_designs_shefa_spec_epic_plan_on_call_emergency_failsafe, docs_designs_shefa_spec_epic_plan_two_directional_emergency_phrases, docs_designs_shefa_spec_epic_plan_emergency_signoff_gate, docs_designs_shefa_spec_epic_plan_call_control [INFERRED 0.85]
- **Fine-tuning order: dialogue, recogniser, voice** — docs_fine_tuning_plan_llm_qlora_receptionist_dialogues, docs_fine_tuning_plan_whisper_lora_phone_augmentation, docs_fine_tuning_plan_piper_voice_talent_finetune [EXTRACTED 1.00]
- **Configuration A: the measured ship-now stack on 12 GB** — docs_model_selection_gemma2_9b, docs_model_selection_omikhan_bangla_asr_whisper_medium, docs_model_selection_stock_whisper_small, docs_model_selection_piper_bn_bd_google_medium, docs_research_bangla_english_voice_models_2026_11_kokoro_82m [EXTRACTED 1.00]
- **Asterisk call path: media, control and outbound dialing** — docs_superpowers_plans_2026_11_01_asterisk_telephony_and_reminders_audiosocket_codec, docs_superpowers_plans_2026_11_01_asterisk_telephony_and_reminders_handle_audiosocket, docs_superpowers_plans_2026_11_01_asterisk_telephony_and_reminders_asterisk_call_leg, docs_superpowers_plans_2026_11_01_asterisk_telephony_and_reminders_originate_call, docs_superpowers_plans_2026_11_01_asterisk_telephony_and_reminders_place_call [EXTRACTED 1.00]
- **Dark-Fill Brand Icons** — console_public_icons_bluesky_icon, console_public_icons_discord_icon, console_public_icons_github_icon, console_public_icons_x_icon [EXTRACTED 1.00]

## Communities (240 total, 61 thin omitted)

### Community 0 - "Call Session Management"
Cohesion: 0.06
Nodes (48): system_prompt(), CallSession, SessionManager, truncate_history(), Turn, build_messages(), _FakeRedisClient, _install_fake_redis() (+40 more)

### Community 1 - "FastAPI App and Calls"
Cohesion: 0.05
Nodes (34): mask_phone(), run_reminders(), _bearer_token(), build_auth_store(), create_app(), api_login(), call_me(), decline_ring() (+26 more)

### Community 2 - "Coverage Policy Gate"
Cohesion: 0.06
Nodes (14): main(), check_report(), load_report(), _normalize(), report_files(), _config(), _report(), test_a_structurally_wrong_report_is_not_silently_accepted() (+6 more)

### Community 3 - "LLM Adapters"
Cohesion: 0.09
Nodes (10): BaseLLM, LLMResult, ToolDefinition, AnthropicLLM, _lang_from_content(), _lang_from_content(), OpenAICompatibleLLM, _lang_from_content() (+2 more)

### Community 4 - "React Owner Console"
Cohesion: 0.06
Nodes (43): dependencies, react@^19.2.8, react-dom@^19.2.8, thinking-orbs@^0.3.2, devDependencies, oxlint@^1.81.0, @types/node@^24.13.3, @types/react@^19.2.18 (+35 more)

### Community 5 - "Spoken Dates and Actions"
Cohesion: 0.09
Nodes (28): bn_digits(), _confirm_book(), _confirm_cancel(), _confirm_departments(), _confirm_doctor_info(), _confirm_doctors(), _confirm_reschedule(), _confirm_slots() (+20 more)

### Community 6 - "Config Loading Tests"
Cohesion: 0.06
Nodes (27): AppConfig, load_config(), _nested_undeclared_keys(), test_app_section_is_retained(), test_config_boots_from_a_fresh_interpreter(), test_default_config_loads(), test_default_config_starts_without_tunnel_env_vars(), test_default_yaml_declares_the_new_telephony_knobs() (+19 more)

### Community 7 - "Settings Config Models"
Cohesion: 0.08
Nodes (36): AnthropicAdapterConfig, AppInfoConfig, AsteriskConfig, AuthPrincipalConfig, CalendarConfig, ComplianceConfig, CustomEHRConfig, EHRConfig (+28 more)

### Community 8 - "Media Queue Concurrency"
Cohesion: 0.11
Nodes (11): make_media_queues(), _start_pipeline(), _stream_sid(), PlaybackWorker, FakeSocket, _frame(), TestAutouseResetFixture, TestBoundedQueues (+3 more)

### Community 9 - "Reminders and Browser Calls"
Cohesion: 0.09
Nodes (17): calls_ringing(), in_quiet_hours(), run_forever(), run_reminder_cycle(), _identify_caller(), BrowserCallLeg, handle_browser_call(), pipeline_factory() (+9 more)

### Community 10 - "AudioSocket Call Simulation"
Cohesion: 0.09
Nodes (17): listen(), main(), run(), silence(), speak(), s16le_16k_mono_to_slin8k(), handle_audiosocket(), pipeline_factory() (+9 more)

### Community 11 - "Asterisk Call Leg"
Cohesion: 0.09
Nodes (19): AsteriskCallLeg, client_factory(), originate_call(), _ari(), _ari_with_caller(), _serve(), test_a_connection_without_a_uuid_is_closed(), test_failed_transfer_never_claims_success() (+11 more)

### Community 12 - "OpenAI-Compatible LLM Tests"
Cohesion: 0.11
Nodes (22): reset_shared_registry(), sample_config(), test_bad_directories_are_named_errors(), _AsyncStream, _chunk(), _collect(), _Completions, _http_error() (+14 more)

### Community 13 - "Shefa CLI Commands"
Cohesion: 0.08
Nodes (26): build_parser(), _build_tts(), configured_roles(), doctor_report(), _hosted_llm(), lab_meta(), _lan_addresses(), main() (+18 more)

### Community 14 - "STT Adapters"
Cohesion: 0.08
Nodes (9): pcm_data_offset(), BaseSTT, language_from_code(), STTResult, ElevenLabsSTT, as_wav(), OpenAISTT, test_language_from_code_maps_en_bn_and_everything_else_to_other() (+1 more)

### Community 15 - "Failure Taxonomy Harness"
Cohesion: 0.13
Nodes (9): _CallHarness, FakeLLM, FakeSTT, FakeTTS, _llm_ok(), _llm_ok_result(), _pcm_chunk(), _RecordingSink (+1 more)

### Community 16 - "Lab Dates and Scenarios"
Cohesion: 0.08
Nodes (9): bn_date(), en_date(), fill(), render(), resolve_day(), _Ears, TestVoiceTest, _Voice (+1 more)

### Community 17 - "Twilio Media and Call Log"
Cohesion: 0.09
Nodes (17): call_ended(), call_started(), default_calls_store(), list_calls(), handle_incoming_call(), media_stream_url(), media_stream_ws(), outbound_twiml() (+9 more)

### Community 18 - "Auth Token Store"
Cohesion: 0.11
Nodes (6): generate_token(), hash_token(), _store(), TestAuthStoreAuthentication, TestHashToken, TestTokenGeneration

### Community 19 - "Lab Scenario Runner"
Cohesion: 0.12
Nodes (11): CheckResult, scenario_checks(), ScenarioResult, Expect, load_scenarios(), parse_scenarios(), Scenario, TestReport (+3 more)

### Community 20 - "Default Pipeline Config"
Cohesion: 0.06
Nodes (36): device, provider, voice_id, confidence_threshold, provider, max_tokens, model, provider (+28 more)

### Community 21 - "Voice Pipeline Streaming"
Cohesion: 0.13
Nodes (11): StreamEvent, VoicePipeline, _FakeTTS, _ScriptedLLM, _Sink, TestGenerateReplyExtractMode, _fake_execute(), TestGenerateReplyNativeMode (+3 more)

### Community 22 - "Calls Store"
Cohesion: 0.12
Nodes (6): set_default_calls_store(), CallsStore, client(), _row(), TestDurableDeleteTombstones, TestTheCallsTable

### Community 23 - "Audio Codec Boundary"
Cohesion: 0.11
Nodes (6): strip_wav_header(), _pcm16(), TestCodecBoundary, TestGoldenFixture, TestStripWavHeader, _wav()

### Community 24 - "Append-Only Audit Table"
Cohesion: 0.12
Nodes (4): utc_day(), TestComplianceAuditLogWritesToTheStore, TestDailyCountReconciliationAgainstTheHeartbeat, TestTheAppendOnlyAuditTable

### Community 25 - "Whisper Confidence Scoring"
Cohesion: 0.09
Nodes (21): _clamp(), _combine_confidence(), _preload_cuda_libraries(), _segment_confidence(), _no_real_cuda_preload(), test_combine_confidence_caps_at_the_weakest_segment(), test_combine_confidence_clamps_a_negative_language_probability(), test_combine_confidence_clamps_out_of_range_input() (+13 more)

### Community 26 - "Model Bench Script"
Cohesion: 0.13
Nodes (19): add_clinic_noise(), bangla_ratio(), cmd_data(), cmd_llm(), cmd_stt(), cmd_tts(), coqui_engine(), error_rates() (+11 more)

### Community 27 - "Telephony Provider Health"
Cohesion: 0.10
Nodes (16): TelephonyProvider, asterisk_status(), database_status(), health_report(), health(), _ari(), test_degraded_when_ari_is_unreachable(), test_degraded_when_the_database_fails() (+8 more)

### Community 28 - "Model Registry and TTS"
Cohesion: 0.09
Nodes (5): BaseTTS, ModelRegistry, AzureTTS, ElevenLabsTTS, TestRegistryInstanceAttrs

### Community 30 - "Piper TTS Adapter"
Cohesion: 0.13
Nodes (4): PiperTTS, TestResultContract, TestLoadIsOffloadedAndRaceFree, slow_load()

### Community 31 - "Reminder Cycle Tests"
Cohesion: 0.12
Nodes (19): pop_context(), book(), test_an_answered_reminder_is_never_repeated(), test_an_appointment_that_has_already_started_is_not_due(), test_app_lifespan_runs_the_reminder_scheduler_when_enabled(), test_appointment_within_the_lead_window_is_due(), test_attempt_cap_and_retry_gap(), test_cancelled_and_far_off_appointments_are_not_due() (+11 more)

### Community 32 - "Audio Frame Streaming"
Cohesion: 0.09
Nodes (5): AudioFrame, TestAudioFrame, synthesize_stream(), synthesize_stream(), RecordingQueue

### Community 33 - "Clinic Directory Import"
Cohesion: 0.11
Nodes (12): import_directory(), _required(), _weekday(), ClinicError, _from_minutes(), _parse_date(), _to_minutes(), test_available_slots_follow_the_weekly_schedule() (+4 more)

### Community 34 - "Audit Store"
Cohesion: 0.11
Nodes (9): AuditStore, default_audit_store(), set_default_audit_store(), test_audit_log_writes_the_event_to_the_durable_store(), audit(), isolated_default(), TestStorageSettings, TestTheDefaultStore (+1 more)

### Community 35 - "Mulaw Audio Conversion"
Cohesion: 0.12
Nodes (9): _from_float(), mulaw8k_to_s16le_16k_mono(), s16le_16k_mono_to_mulaw8k(), _to_float(), to_s16le_16k_mono(), word_error_rate(), _words(), _silence() (+1 more)

### Community 36 - "STT Confidence Tests"
Cohesion: 0.15
Nodes (16): needs_repeat(), FakeInfo, FakeModel, FakeSegment, make_stt(), test_bangla_transcript_keeps_its_language(), test_confidence_accounts_for_no_speech_probability(), test_confidence_accounts_for_segment_logprob() (+8 more)

### Community 37 - "Twilio Inbound Decoding"
Cohesion: 0.09
Nodes (6): decode_inbound_media(), _mulaw(), process_audio_stream(), TestInboundDecode, TestMediaStreamMessageFlow, _tone()

### Community 38 - "TTS Persistent Session"
Cohesion: 0.14
Nodes (4): TestPersistentSession, TestSynthesize, TestSynthesizeStream, synthesize()

### Community 39 - "PHI Compliance Utilities"
Cohesion: 0.11
Nodes (15): audit_log(), hash_identifier(), _keep_last_four(), mask_phi(), validate_phi_access(), test_hash_identifier(), test_mask_bd_e164_phone_keeps_only_the_last_four(), test_mask_dob() (+7 more)

### Community 40 - "Bench Evaluation"
Cohesion: 0.16
Nodes (6): BenchResult, evaluate(), Threshold, run_bench(), TestEvaluate, TestFormatting

### Community 41 - "Whisper Local Loading"
Cohesion: 0.11
Nodes (10): WhisperLocalSTT, test_a_cpu_load_does_not_preload_cuda(), test_a_cpu_load_failure_propagates(), test_a_gpu_load_failure_falls_back_to_cpu(), test_close_releases_the_model(), test_empty_text_detects_english_with_zero_confidence(), test_ensure_model_loads_faster_whisper_once(), test_explicit_device_defaults_compute_type_to_float16() (+2 more)

### Community 42 - "Booking Confirmation Text"
Cohesion: 0.12
Nodes (5): confirmation_text(), test_a_single_doctor_match_gets_the_full_schedule(), TestConfirmationText, TestDirectoryConfirmations, TestSlotAnswers

### Community 43 - "Emergency Detection Corpus"
Cohesion: 0.11
Nodes (17): evaluate_transcript(), is_emergency(), test_a_language_with_no_configured_keywords_never_escalates(), test_benign_urgent_bangla_does_not_escalate(), test_benign_urgent_english_does_not_escalate(), test_canonical_bangla_phrase_escalates(), test_canonical_english_phrase_escalates(), test_empty_or_whitespace_utterance_never_escalates() (+9 more)

### Community 44 - "Speak-To Playback Tests"
Cohesion: 0.14
Nodes (4): speak_to(), FakeTTS, RecordingSink, TestSpeakTo

### Community 45 - "VRAM Measurement"
Cohesion: 0.14
Nodes (5): read_vram_fraction(), _sequence(), TestVram, TestVramAttribution, TestVramFallbackLadder

### Community 46 - "Asterisk Telephony Plan"
Cohesion: 0.10
Nodes (20): Asterisk + Bangladeshi SIP trunk setup guide, shefa asterisk render CLI, Softphone over Wi-Fi (Linphone/Zoiper, extension 1001, dial 1000), telephony.asterisk settings (ari_password, trunk_endpoint, caller_id), Carrier permission for automated reminder calls, BTRC-licensed IPTSP (Amber IT, BDCOM, BRACNet, MetroNet), Carrier comparison table, SHEFA SIP trunk inquiry (Bangla + English email and phone script) (+12 more)

### Community 47 - "Pipeline Language Detection"
Cohesion: 0.10
Nodes (5): detect_language(), TranscriptDecision, _discard(), _SilentTTS, _SynthesisError

### Community 48 - "PHI Access Authorization"
Cohesion: 0.10
Nodes (4): AuthStore, client(), TestValidatePhiAccessIsARealDecision, _viewer_store()

### Community 49 - "Other-Language Routing Tests"
Cohesion: 0.11
Nodes (9): _FakeLLM, _FakeSTT, _FakeTTS, _FakeWhisper, _pcm_chunk(), _RecordingSink, test_detect_language_classifies_non_en_bn_scripts_as_other(), test_other_language_offers_warm_transfer_and_never_replies() (+1 more)

### Community 50 - "Model Adapter Config"
Cohesion: 0.08
Nodes (24): llm_anthropic, llm_openai, stt_elevenlabs, stt_openai, tts_elevenlabs, tts_piper, tts_vits, api_key (+16 more)

### Community 51 - "Open-Weight LLM Research"
Cohesion: 0.10
Nodes (17): 12 GB card Ollama settings (flash attention, q8_0 KV, keep alive), aya-expanse:8b, gemma2:9b, gemma-3-12b-it (Q4_K_M), qwen2.5:7b, Qwen3-8B with default thinking mode, Router prompt bench in production JSON mode (12 cases), TigerLLM-9B (+9 more)

### Community 52 - "Lead Sink and Dashboard"
Cohesion: 0.12
Nodes (15): E10 Resample Pipeline + Retention Hygiene, E9 Heartbeat, Backup + Supervisor, E11 Synthetic Fixture + Blind Gold Re-code, T2 SQLite Call-Log Sink, X3 Canonical 6-Value Disposition Enum, E6 Cloud Escape Restricted to Synthetic Audio, D6 Daily Coder Workflow, D4 Today's Calls Dashboard Contract (+7 more)

### Community 53 - "Failure Taxonomy"
Cohesion: 0.11
Nodes (5): backoff_delay(), FailureKind, MalformedLLMOutputError, require_llm_result(), TestFailureTaxonomy

### Community 54 - "Voice Model Fetching"
Cohesion: 0.11
Nodes (11): run_fetch_models(), azure_check(), configured_voices(), fetch_all(), fetch_voice_for(), _http_get_json(), kokoro_check(), speech_runtime_check() (+3 more)

### Community 55 - "Clinic Store Core"
Cohesion: 0.13
Nodes (7): ClinicStore, _resolve_doctor(), clinic(), test_context_manager_closes_the_connection(), test_departments_and_doctors_come_from_the_directory(), test_find_doctor_ignores_titles_and_matches_bangla(), store()

### Community 56 - "Model Warmup Tests"
Cohesion: 0.12
Nodes (8): pings(), _Registry, _Stt, _stub_router(), test_a_failed_stage_is_skipped_not_raised(), test_run_forever_pings_again(), test_warm_models_loads_each_stage(), _Tts

### Community 57 - "API Error Envelope"
Cohesion: 0.11
Nodes (6): _bearer(), client(), TestEveryErrorWearsTheEnvelope, TestFastAPIValidationIsEnveloped, TestTheMigrationListIsDeclared, TestTheStatusMapIsTheSingleSourceOfTruth

### Community 58 - "Appointment Booking Tests"
Cohesion: 0.21
Nodes (14): SlotUnavailableError, _patient(), test_a_failed_reschedule_keeps_the_original(), test_a_patient_cannot_touch_someone_elses_appointment(), test_a_race_on_reschedule_is_reported_and_leaves_the_original(), test_a_taken_or_unscheduled_slot_is_refused(), test_booking_takes_the_slot_and_returns_a_speakable_id(), test_cancel_frees_the_slot_and_cannot_repeat() (+6 more)

### Community 60 - "Fake Piper Voices"
Cohesion: 0.12
Nodes (14): _fixed_voice(), synthesize(), _multi_voice(), synthesize(), voice(), FakeAudioChunk, FakePiperVoice, counting_load() (+6 more)

### Community 61 - "Telephony Router Gating"
Cohesion: 0.13
Nodes (3): store(), TestTelephonyRouterGating, _toggle_dev_config()

### Community 62 - "CI Workflow"
Cohesion: 0.09
Nodes (21): concurrency, cancel-in-progress, group, jobs, test, name, on, pull_request (+13 more)

### Community 63 - "LLM Pull Status"
Cohesion: 0.12
Nodes (4): llm_status(), pull_llm(), TestLanguageModel, get_json()

### Community 65 - "Action Argument Resolution"
Cohesion: 0.13
Nodes (7): extractor_system_prompt(), resolve_arguments(), resolve_relative_day(), _router_parameters(), TestExtractorPrompt, TestResolveArguments, TestResolveRelativeDay

### Community 66 - "Energy VAD"
Cohesion: 0.19
Nodes (6): EnergyVAD, _noise_chunk(), _pcm16(), TestEnergyVADUnit, _tone_chunk(), _warmup_noise()

### Community 67 - "Structured Logging and Masking"
Cohesion: 0.13
Nodes (6): _mask_event_dict(), setup_logging(), log_capture(), TestSetupLoggingChoosesTheRendererByStream, TestSetupLoggingHonoursThePhiMaskingFlag, _TtyLike

### Community 68 - "Text Chat Tests"
Cohesion: 0.10
Nodes (6): chat(), _Script, test_a_failed_reply_is_a_503_and_leaves_the_history_resendable(), test_a_typed_booking_lands_in_the_clinic_store(), test_the_phone_number_identifies_the_patient_on_the_first_message(), _tomorrow()

### Community 69 - "Owner Console Plan"
Cohesion: 0.11
Nodes (10): Call log and owner API (/api/v1/calls, /api/v1/appointments), Audit-verified backend gaps (no leads, hours, persistence, browser auth, i18n, UI tests), Bangla Piper voice bn_BD.nf_cycgan.onnx named blocker, CallControl process-global leg registry and CallLeg interface, SIP trunk and FreeSWITCH bridge unlanded, Lead correction workflow (lead_corrections audit rows), Multi-clinic tenancy (clinic_id on all tables), CEO Plan: SHEFA Owner Console and Lead Operations (+2 more)

### Community 70 - "Language Detector Tests"
Cohesion: 0.15
Nodes (13): Language, ModelProvider, needs_escalation(), test_detect_bangla(), test_detect_code_switching(), test_detect_english(), test_emergency_detection(), test_needs_escalation_emergency() (+5 more)

### Community 71 - "Tool Executor"
Cohesion: 0.18
Nodes (14): on_call_target(), _acting_patient(), _book_appointment(), _cancel_appointment(), _check_appointment_slots(), _get_doctor_info(), _list_departments(), _list_doctors() (+6 more)

### Community 72 - "Twilio Stream Addressing"
Cohesion: 0.11
Nodes (5): _HeldOpenSocket, _Socket, TestStreamAddressing, process_audio_stream(), process_audio_stream()

### Community 73 - "Escalation Config"
Cohesion: 0.10
Nodes (20): bn, en, escalation, emergency_keywords, hold_audio_url, max_transfer_attempts, on_call_numbers, other_language_prompt (+12 more)

### Community 74 - "Console App TS Config"
Cohesion: 0.10
Nodes (19): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection (+11 more)

### Community 75 - "First-Clinic Epic"
Cohesion: 0.12
Nodes (13): Approach B: The Booking Engine, T3 Bangla Booking-Loop Quality Bar, Booking as Revenue Unit, Conviction Sale Posture, SHEFA First-Clinic Original-Item Disposition Table, SHEFA First-Clinic Strategy: Shadow Line + Door-Opener, T5 20-Minute HMS Discovery, Land-and-Expand via Complementary HMS Wedge (+5 more)

### Community 76 - "Bangla ASR Research"
Cohesion: 0.12
Nodes (16): Whisper LoRA with phone-line augmentation, fetch_stt_model.py CTranslate2 packaging and tokenizer guard, OmiKhan/bangla-asr-whisper-medium, Stock Whisper large-v3, Stock Whisper small, ASR research notes (Bangla + English + Banglish), large-v3-turbo and distil-large-v3 int8 (English path), Bangla telehealth 8 kHz study (MDPI Signals 7(3):44) (+8 more)

### Community 77 - "Console API Tests"
Cohesion: 0.14
Nodes (11): FakePipeline, signed_in(), test_browser_call_streams_audio_both_ways(), test_browser_provider_dials_by_ringing(), test_console_leg_refuses_transfers_honestly(), test_directory_lists_departments_doctors_and_schedules(), test_lan_addresses_skip_loopback_and_survive_a_dns_failure(), test_reminders_run_rings_the_console_when_provider_is_browser() (+3 more)

### Community 78 - "Voice Flow Tests"
Cohesion: 0.18
Nodes (14): _identify(), _spoken(), test_a_slow_router_gets_a_spoken_filler_before_the_answer(), slow_generate(), test_an_unidentified_caller_is_asked_for_a_number_not_acted_for(), test_cancel_with_two_bookings_asks_which_and_with_none_says_so(), test_cancel_without_a_reference_cancels_the_callers_only_booking(), test_filler_can_be_turned_off() (+6 more)

### Community 79 - "Lab Report Rendering"
Cohesion: 0.24
Nodes (11): _audio(), _bubble(), _checks_html(), _median(), _ms(), render_html(), results_json(), summarise() (+3 more)

### Community 80 - "Twilio Webhook Tests"
Cohesion: 0.15
Nodes (9): client(), _patch_http_client(), _set_account_sid(), _StubAsyncClient, test_incoming_call_returns_text_xml_stream_twiml(), test_outbound_twilio_error_propagates(), test_outbound_twiml_returns_text_xml_stream_twiml(), test_outbound_uses_the_configured_public_url() (+1 more)

### Community 81 - "Clinic EHR Integration"
Cohesion: 0.20
Nodes (10): default_clinic_store(), set_default_clinic_store(), _doctor_card(), get_doctor_info(), get_patient_history(), list_departments(), list_doctors(), verify_patient() (+2 more)

### Community 82 - "Language-Routed STT"
Cohesion: 0.19
Nodes (5): LanguageRoutedSTT, pick_language(), _Stt, TestLanguagePick, TestRoutedSpeech

### Community 83 - "Whisper Transcribe Fallback"
Cohesion: 0.11
Nodes (5): test_a_cpu_inference_failure_propagates(), test_a_gpu_inference_failure_rebuilds_on_cpu_and_retries(), test_transcribe_loads_the_model_on_first_use(), test_transcribe_of_a_buffer_with_no_usable_pcm_is_empty(), test_transcribe_stream_delegates_to_transcribe()

### Community 84 - "Authorized API Access"
Cohesion: 0.19
Nodes (3): _bearer(), TestAuthorizedAccess, fake_call()

### Community 85 - "Telephony Config"
Cohesion: 0.11
Nodes (18): host, password, port, username, telephony, provider, public_url, sip (+10 more)

### Community 86 - "Appointment Status Store"
Cohesion: 0.18
Nodes (5): format_appointment_id(), NotFoundError, parse_appointment_id(), test_appointment_ids_round_trip_and_unknown_ids_are_not_found(), test_schedule_lists_days_in_order()

### Community 87 - "Language-Routed TTS"
Cohesion: 0.20
Nodes (4): LanguageRoutedTTS, script_language(), TestScriptRouting, _Voice

### Community 88 - "CLI Bench Tests"
Cohesion: 0.17
Nodes (4): FakeTTS, _returns(), TestModuleEntryPoint, TestRunBench

### Community 90 - "Console Node TS Config"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+8 more)

### Community 91 - "Demo and Fine-Tuning Guides"
Cohesion: 0.15
Nodes (14): Showing SHEFA to a client (demo guide), Conversation lab (shefa lab run), Lab scenarios (configs/lab/scenarios.yaml), Live console demo (type, talk, have the agent call me), Fine-tuning plan (12 GB GPU), LLM QLoRA on receptionist dialogues, What to measure on the real 12 GB card (10-item checklist), Keep the measured stack, then fine-tune (research report) (+6 more)

### Community 92 - "Local Telephony Child Epic"
Cohesion: 0.13
Nodes (14): E2 ANI Reliability + Hashed Dedup, D7 Degraded-Forwarding Fallback, E4 Honest Forward Semantics + verified_rings, T1 BD Number + Forward-on-No-Answer Verification, Sub-2-Ring Truncation Blind Spot, E1 Webhook HMAC + Idempotency + Dashboard Auth, AsteriskARIAdapter, CallControl Plane (+6 more)

### Community 93 - "Voice Registry Config"
Cohesion: 0.21
Nodes (4): TTSConfig, VoiceConfig, TestRegistry, TestVoiceConfig

### Community 94 - "Lab Execution"
Cohesion: 0.18
Nodes (3): Lab, lab(), make()

### Community 95 - "Voice Fetch Tests"
Cohesion: 0.18
Nodes (7): directory(), fetch_voice(), _piper_download(), _present(), _fake_download(), TestFetchVoice, download()

### Community 96 - "Action Parsing Tests"
Cohesion: 0.18
Nodes (5): parse_action(), _unfence(), test_a_tool_without_arguments_is_still_an_action(), test_parse_action_accepts_a_fenced_json_block(), TestParseAction

### Community 97 - "API Endpoint Tests"
Cohesion: 0.15
Nodes (8): client(), _local_store(), auth(), _store(), test_call_me_falls_back_to_configured_number(), test_call_me_has_no_hardcoded_default_number(), test_call_me_uses_verified_number(), fake_call()

### Community 99 - "TTS Failure Voices"
Cohesion: 0.13
Nodes (5): ExplodingVoice, fake_voice(), HardFailVoice, TestStreamAlwaysTerminates, TestStreamErrorPropagation

### Community 100 - "Token Verification"
Cohesion: 0.17
Nodes (5): _parse_record(), TokenError, verify_token(), TestVerifyToken, test_setup_writes_a_private_config_with_a_working_token()

### Community 101 - "App and Session Config"
Cohesion: 0.12
Nodes (15): app, debug, environment, name, version, models, routing, fallback_provider (+7 more)

### Community 102 - "Bangla Datasets and Licences"
Cohesion: 0.15
Nodes (13): Piper fine-tune on a Bangladeshi voice talent, Bangla-Instruct (conflicting licences), BanglaKontho (20 h single speaker, CC BY-NC 4.0), Bangla datasets and fine-tuning recipes notes, IndicTTS Bengali (commercial use needs an MoU), IndicVoices-R (CC BY 4.0), Bengali.AI OOD-Speech (about 1,201 h), OpenSLR 37 Google crowd-sourced Bengali TTS (+5 more)

### Community 103 - "Asterisk Config Rendering"
Cohesion: 0.18
Nodes (8): render_asterisk_config(), template_dir(), test_missing_variables_are_all_named(), test_public_ip_sets_the_nat_addresses_and_port_can_change(), test_renders_trunk_audiosocket_and_ari(), test_softphone_extension_is_rendered_only_when_a_password_is_given(), test_the_kit_in_the_repo_never_contains_a_password(), test_without_a_trunk_only_the_ari_password_is_needed_and_no_trunk_is_rendered()

### Community 104 - "Pipeline Reply Generation"
Cohesion: 0.20
Nodes (3): list_tools(), get_tool_definitions(), test_routing_hints_appear_only_for_tools_that_exist()

### Community 105 - "Standalone Pipeline Script"
Cohesion: 0.18
Nodes (13): main(), test_config(), test_full_pipeline(), test_language_detector(), test_llm(), test_session(), test_stt(), test_tts() (+5 more)

### Community 106 - "Calendar Integration"
Cohesion: 0.25
Nodes (6): book_appointment(), cancel_appointment(), check_slots(), _patient_id(), reschedule_appointment(), send_confirmation()

### Community 107 - "Model Fetch Checks"
Cohesion: 0.19
Nodes (6): Check, TestCheckLine, TestDoctorLanguageModel, TestDoctorVoices, TestFetchModelsCommand, fetch_all()

### Community 108 - "VITS Voice Fetching"
Cohesion: 0.18
Nodes (3): fetch_vits_voice(), _hf_snapshot(), TestVoicesOfEveryKind

### Community 109 - "Twilio Helper Coverage"
Cohesion: 0.13
Nodes (3): _make_capture(), _width_for(), TestHelperCoverage

### Community 110 - "Clinic Example Config"
Cohesion: 0.13
Nodes (14): departments, doctors, name, name_bn, leave, name, name_bn, qualification (+6 more)

### Community 111 - "Demo Deliverable Gates"
Cohesion: 0.16
Nodes (9): Approach D: After-Hours Receiver, D2 One-Page Bangla Pitch, D1 Five-Beat Demo Storyboard, T8 Weekly Go/No-Go Progress Metrics, Go / No-Go Gate (First-Clinic), T6 Outreach Tracker + Objection Coding, Revised Go / No-Go Gate (One-Wedge), Child 6: Demo Deliverable (+1 more)

### Community 112 - "Developer Loop Child Epic"
Cohesion: 0.17
Nodes (3): Child 0: Developer Loop (shefa doctor / replay / bench / serve), HTTP Error Envelope + Status Map, Named External Blockers

### Community 114 - "README Operations Roadmap"
Cohesion: 0.13
Nodes (15): Bangla quality roadmap item, Blind voice test, Conversation lab, First-clinic disposition document, Fully local quick start, OpenAI demo quick start, PHI masking and audit trail, Production checklist (+7 more)

### Community 115 - "Test Call Page"
Cohesion: 0.16
Nodes (9): Twilio development sink, console play(), console startCall(), console PCM16 16 kHz AudioWorklet, test center downsample(), test center playMulaw(), test center voiceHangup(), test center voiceToggle() (+1 more)

### Community 116 - "Bench Subprocess Runner"
Cohesion: 0.18
Nodes (6): _machine_used_vram_mb(), _process_vram_mb(), _run(), _total_vram_mb(), run(), calls()

### Community 117 - "Startup Model Warmup"
Cohesion: 0.17
Nodes (8): _lifespan(), ping_llm(), run_forever(), warm_models(), llm(), warmup_enabled(), test_app_lifespan_is_inert_for_twilio(), test_app_lifespan_runs_the_audiosocket_server_for_asterisk()

### Community 118 - "Hosted Provider Tests"
Cohesion: 0.16
Nodes (9): ssml(), _azure(), test_a_hosted_model_is_never_pinged_like_ollama(), test_an_unknown_language_tag_is_reported_as_english(), test_azure_errors_reach_the_caller(), test_azure_reads_its_key_and_region_from_the_environment(), test_azure_streams_pcm_without_splitting_samples(), test_ssml_escapes_text_and_uses_the_voice_locale() (+1 more)

### Community 119 - "Action Extraction Tests"
Cohesion: 0.25
Nodes (5): extract_action(), ExtractedAction, _FakeRouterLLM, _session(), TestExtractAction

### Community 120 - "Call Dial Routing Tests"
Cohesion: 0.13
Nodes (9): _staffed_on_call(), test_dial_routes_to_the_leg(), test_dial_to_unknown_call_reports_an_error(), test_emergency_transfer_plays_hold_then_releases_the_leg(), test_get_returns_none_for_an_unregistered_call(), test_hangup_to_unknown_call_reports_an_error(), test_play_file_to_unknown_call_reports_an_error(), test_release_is_idempotent() (+1 more)

### Community 121 - "Media Stream Cancellation"
Cohesion: 0.13
Nodes (3): _FakeWebSocket, test_media_stream_cancels_the_pipeline_task_on_disconnect(), test_media_stream_releases_the_leg_on_disconnect()

### Community 122 - "Active Call Tracking"
Cohesion: 0.16
Nodes (8): RecordingLeg, test_active_call_count_tracks_releases(), test_active_call_sids_lists_live_legs(), test_control_registers_and_releases_a_leg(), test_hangup_routes_to_the_leg(), test_play_file_routes_to_the_leg(), test_releasing_one_leg_does_not_release_another(), test_transfer_routes_to_the_leg()

### Community 123 - "Receptionist System Prompt"
Cohesion: 0.18
Nodes (10): Session placeholders language and patient_name, SHEFA Receptionist system prompt, Bilingual emergency detection, EN/BN language detection and code-switching, LLM tool functions, Redis and in-memory session management, Voice pipeline, Demo safety sign-off (+2 more)

### Community 124 - "Config Merge and Env"
Cohesion: 0.14
Nodes (5): AuthConfig, _deep_merge(), _resolve_env_vars(), _strip_wrapping_quotes(), test_dev_mode_placeholder_without_a_fallback_is_not_dev_mode()

### Community 125 - "Telephony Config Tests"
Cohesion: 0.15
Nodes (6): TelephonyConfig, test_a_clean_non_twilio_config_is_valid(), test_public_url_is_an_explicit_validated_config_key(), test_telephony_provider_is_a_single_enum_knob(), test_telephony_provider_rejects_an_unknown_knob_value(), test_two_provider_knobs_is_rejected_at_startup()

### Community 126 - "Twilio Leg Tests"
Cohesion: 0.22
Nodes (8): _ok(), stub(), test_dial_delegates_to_outbound_call(), test_hangup_completes_the_call(), test_play_file_sends_play_twiml(), test_provider_failure_raises_for_the_control_layer_to_catch(), test_register_call_handler_round_trips(), test_transfer_dials_the_target_via_rest()

### Community 127 - "VITS TTS Adapter"
Cohesion: 0.15
Nodes (3): checkpoint_files(), VITSTTS, tts()

### Community 129 - "Clinic Integration Tests"
Cohesion: 0.20
Nodes (7): _next_monday(), seeded(), test_booking_cancel_and_reschedule_round_trip(), test_booking_needs_a_patient_and_an_unambiguous_doctor(), test_history_lists_only_the_patients_own_appointments(), test_other_patients_cannot_cancel_or_move_my_booking(), _verify()

### Community 130 - "Lab Turn Checks"
Cohesion: 0.33
Nodes (5): has_devanagari(), turn_checks(), TurnRecord, _record(), TestTurnChecks

### Community 131 - "Speech Model Fetch"
Cohesion: 0.21
Nodes (6): fetch_speech_model(), result(), step(), run(), TestSpeech, run()

### Community 132 - "Threaded TTS Wrapper"
Cohesion: 0.23
Nodes (4): stream_in_thread(), offer(), pump(), ThreadedTTS

### Community 133 - "Twilio Call Leg"
Cohesion: 0.26
Nodes (4): _dial_twiml(), _play_twiml(), register_call_handler(), TwilioCallLeg

### Community 134 - "CLI Bench Command Tests"
Cohesion: 0.21
Nodes (4): _bench_returning(), _capturing_report(), TestBenchCommand, run_bench()

### Community 137 - "Scripted Voice Calls"
Cohesion: 0.15
Nodes (5): call(), say(), _Script, _sink(), _Tts

### Community 138 - "Text Chat and Console Docs"
Cohesion: 0.18
Nodes (11): Bangla React console entry page, React Compiler left disabled, Type-aware Oxlint configuration, React TypeScript Vite template, Owner web console, POST /api/v1/chat typed turn endpoint, console addMsg(), SHEFA Console page (+3 more)

### Community 139 - "Free Demo Providers"
Cohesion: 0.26
Nodes (9): shefa setup profiles (local, gemini, groq, openai, azure voices), Azure AI Speech F0 (bn-BD Nabanita and Pradeep neural voices), edge-tts (unofficial endpoint), ElevenLabs Free and Scribe v2, Free-tier cloud fallback notes, Gemini API free tier, Gemini TTS (bn-BD, preview), Google Chirp 3 (STT bn-BD batch only, TTS bn-IN) (+1 more)

### Community 140 - "Safety-Net Child Epic"
Cohesion: 0.18
Nodes (7): Safety-Net Agent Behavior, Name-Callback-Reason Capture Loop, Degrade-to-Transfer Path, Emergency Transfer, No Medical Advice, Child 2: Safety-Net Conversation, DRY_RUN Rehearsal Flag, Read-Back DTMF Key Map

### Community 141 - "Queue Bounds Brief"
Cohesion: 0.17
Nodes (8): T16: 41-item disposition table, T17: models.adapters as single source of truth, Brief T18: bounded queues, put timeouts, concurrency assert, Model bench harness (scripts/bench_models.py), FLEURS bn_in and clinic test data (clean, phone, phone_noise), parse_action Markdown code fence bug, Build order: Child 0, Child 3, Child 5, Child 4, Handoff returns sent:true without sending

### Community 142 - "Project Memory Brief"
Cohesion: 0.17
Nodes (11): Local mode hardware requirements, 9 LLM tool functions list, Local and cloud pipeline providers, SHEFA project brief, Twilio Media Streams call architecture, Asterisk PBX integration, Gemini and Groq free-tier profiles, Model registry and adapter layer (+3 more)

### Community 144 - "UTC Day Boundary"
Cohesion: 0.24
Nodes (4): test_audit_rows_land_on_their_own_utc_day_at_every_hour(), test_call_rows_land_on_their_own_utc_day_at_every_hour(), test_the_local_timezone_does_not_shift_the_day_boundary(), _ts()

### Community 146 - "CLI Argument Parsing"
Cohesion: 0.18
Nodes (3): FakeChunk, FakeVoice, TestArgumentParsing

### Community 147 - "LLM Base Tests"
Cohesion: 0.26
Nodes (4): _events(), _GenerateOnlyLLM, test_the_default_bridges_a_result_to_one_event(), test_the_default_is_null_safe_for_a_malformed_result()

### Community 149 - "Fake WebSocket Media Tests"
Cohesion: 0.18
Nodes (3): _FakeWebSocket, test_media_stream_does_not_leak_the_leg_on_a_provider_error(), test_media_stream_does_not_leak_the_leg_when_the_pipeline_task_dies()

### Community 150 - "LLM Adapter Resolution"
Cohesion: 0.20
Nodes (6): ModelsConfig, test_every_adapter_model_forbids_unknown_keys(), test_every_submodel_forbids_unknown_keys(), test_resolve_llm_adapter_rejects_unregistered_provider(), test_resolve_llm_adapter_requires_exactly_one_adapter(), test_unknown_adapter_type_is_rejected()

### Community 151 - "Integrations Config"
Cohesion: 0.18
Nodes (11): google, provider, api_key, base_url, custom, provider, calendar_id, credentials_path (+3 more)

### Community 152 - "Monitoring Config"
Cohesion: 0.18
Nodes (11): format, level, phi_masking, monitoring, logging, prometheus, sentry, enabled (+3 more)

### Community 153 - "Safety-Net Wedge Approaches"
Cohesion: 0.18
Nodes (7): Approach A: The Door-Opener, Approach C: The Shadow Line, Approach A: Safety-Net Capture (Chosen), Approach C: Demo Theater + Shadow Line, Callback Lead Value Unit, Global Safety-Net Tier Benchmarks (MedCalls, Sully.ai, Clara, VoxAI, AI VOX), Unmanned Windows (Lunch, Prayer, Shift Handover)

### Community 154 - "Owner Console Page"
Cohesion: 0.22
Nodes (9): Booking engine, Clinic directory, Outbound reminder and follow-up scheduler, SHEFA medical voice agent, console api(), console loadAppts(), console loadDir(), console Run reminders now action (+1 more)

### Community 156 - "Legacy Dashboard Sessions"
Cohesion: 0.20
Nodes (9): console loadCalls(), console loadStatus(), dashboard checkHealth(), SHEFA legacy dashboard page, dashboard loadAllSessions(), dashboard loadTools(), dashboard refreshSessions(), SHEFA Test Center page (+1 more)

### Community 157 - "Tool Transfer Tests"
Cohesion: 0.18
Nodes (7): execute_tool(), test_on_call_target_comes_from_config(), test_transfer_to_human_does_not_claim_success_without_a_leg(), test_transfer_to_human_tool_reaches_the_provider(), test_transfer_to_human_tool_reports_a_provider_failure(), test_transfer_to_human_without_a_staffed_target_is_not_claimed(), test_executor_routes_the_new_tools_and_sets_the_session_patient()

### Community 159 - "Outbound Reminder Pipeline"
Cohesion: 0.18
Nodes (5): test_outbound_context_shapes_the_greeting_and_the_session(), sink(), synthesize_stream(), test_pipeline_builds_its_vad_for_16khz_audio(), __init__()

### Community 160 - "Local TTS Research"
Cohesion: 0.27
Nodes (9): Blind voice listening test (shefa lab voices), bangla-speech-processing VITS voices (female/male), Model selection, measured 2026-10-31, Piper bn_BD-google-medium, Kokoro-82M, BnTTS (XTTS-based Bangla), Indic Parler-TTS, No Bengali entry in the official Piper voice list (+1 more)

### Community 161 - "CLI Doctor Speech Tests"
Cohesion: 0.27
Nodes (4): _doctor_returning(), doctor_report(), TestDoctorCommand, TestDoctorSpeechModel

### Community 164 - "Model Fetch Module"
Cohesion: 0.25
Nodes (3): llm_check_for(), hosted_key(), test_hosted_key_ignores_the_local_placeholder()

### Community 165 - "Latency Ceiling Decisions"
Cohesion: 0.25
Nodes (6): E12 Automated Test List + N=2 VRAM Smoke, D8 Latency Ceiling Pin, SF_N_RINGS / SF_LATENCY_MS / SF_SPEND_CAP Config Keys, T4 Cloud-vs-Local Smoke Test, E8 Automated Spend Guard, X2 Twilio-BD Fallbacks + Smoke Verdict Record

### Community 166 - "Runbook Child Epic"
Cohesion: 0.28
Nodes (7): X6 Canonical Build Spec + Dashboard Data Contract, X8 dev/README Copy-Paste Docs, X4 Error-Path Table + Quiet-vs-Dead Rule, X7 ops/runbook.md Living Doc, E7 3rd+ Concurrent Metadata-Only Capture, X1 Week One Build / Runbook, Child 5: Runbook + Dev Docs

### Community 167 - "OpenAI LLM Tests"
Cohesion: 0.31
Nodes (4): _key(), _llm(), test_a_router_call_sends_no_tools_field(), test_tools_are_sent_when_there_are_some()

### Community 168 - "Router Bench Script"
Cohesion: 0.39
Nodes (4): ask(), main(), schema(), score()

### Community 171 - "Legacy Dashboard Views"
Cohesion: 0.22
Nodes (5): dashboard makeOutboundCall(), dashboard renderSessions(), dashboard showToast(), dashboard viewConversation(), test center outboundCall()

### Community 172 - "Media Queue Stall Tests"
Cohesion: 0.25
Nodes (4): MediaQueues, test_a_stalled_playback_consumer_times_out_instead_of_hanging(), _drive(), synthesize_stream()

### Community 173 - "Test Isolation Fixtures"
Cohesion: 0.28
Nodes (3): _isolate_the_default_audit_store(), _isolate_the_default_calls_store(), _isolate_the_default_clinic_store()

### Community 174 - "API Auth Shared Store"
Cohesion: 0.28
Nodes (3): client(), shared_store(), _store()

### Community 177 - "Clinic Loader Tests"
Cohesion: 0.22
Nodes (6): store(), test_cli_import_and_show(), test_cli_import_failures_exit_nonzero(), test_empty_directory_imports_nothing(), test_import_builds_the_whole_directory(), test_reimport_restates_schedule_and_keeps_appointments()

### Community 178 - "OpenAI STT Confidence"
Cohesion: 0.22
Nodes (5): _openai_result(), test_openai_clear_speech_is_confident_not_asked_to_repeat(), test_openai_likely_silence_is_not_confident(), test_openai_request_is_a_multipart_upload_of_a_real_wav_file(), test_openai_without_segments_trusts_only_non_empty_text()

### Community 180 - "Auth Config"
Cohesion: 0.25
Nodes (8): auth, bind_host, dev_mode, principals, roles, admin, clinician, viewer

### Community 181 - "Compliance Config"
Cohesion: 0.25
Nodes (8): compliance, audit_log_enabled, call_recording_consent_required, data_retention_days, encryption_algorithm, hipaa_enabled, max_session_ttl, phi_access_logging

### Community 182 - "Notification Config"
Cohesion: 0.25
Nodes (8): from_address, provider, smtp_host, smtp_port, notifications, email, sms, provider

### Community 183 - "Console Icon Sprite"
Cohesion: 0.25
Nodes (8): Bluesky Clip Path, Bluesky Icon Symbol, Discord Icon Symbol, Documentation Icon Symbol, GitHub Icon Symbol, Social Icon Symbol, Console SVG Icon Sprite, X Icon Symbol

### Community 184 - "STT Model Fetch Script"
Cohesion: 0.43
Nodes (3): convert(), _digest(), main()

### Community 185 - "Twilio Config Tests"
Cohesion: 0.29
Nodes (4): TwilioConfig, test_media_stream_url_derives_from_account_sid_when_unset(), test_media_stream_url_must_be_wss(), test_twil_io_media_stream_rejected_when_provider_is_not_twilio()

### Community 186 - "Error Text Tests"
Cohesion: 0.36
Nodes (3): error_text(), test_ambiguous_and_missing_appointments_have_their_own_sentences(), TestErrorText

### Community 189 - "Language Greeting Config"
Cohesion: 0.29
Nodes (7): bn, en, languages, code_switching, default_greeting, primary, supported

### Community 190 - "Asterisk Docker Compose"
Cohesion: 0.29
Nodes (6): image, network_mode, restart, volumes, services, asterisk

### Community 191 - "Disclosure Approval Gate"
Cohesion: 0.29
Nodes (5): E5 Disclosure-Failure Terminate + Pre-Rendered Clips, Draft Pricing Tiers, Final Approval Gate (2026-09-23), X5 Two-Failed-Parses Handoff, D3 Post-Disclosure Warm Close + Reveal Scripts

### Community 192 - "Lab Voice Test Page"
Cohesion: 0.38
Nodes (3): _voice_test(), render(), write_page()

### Community 193 - "Patient Records Store"
Cohesion: 0.29
Nodes (3): normalize_phone(), test_patients_are_found_by_phone_and_names_fill_in_once(), test_phone_numbers_are_normalised_so_one_person_is_one_patient()

### Community 194 - "Lab Transcript Measures"
Cohesion: 0.29
Nodes (3): _clean_patient_line(), latin_share(), TestMeasures

### Community 200 - "English Whisper Config"
Cohesion: 0.33
Nodes (6): stt_whisper_english, bangla_finetuned, compute_type, device, model_size, type

### Community 201 - "Local Whisper Config"
Cohesion: 0.33
Nodes (6): stt_whisper_local, bangla_finetuned, compute_type, device, model_size, type

### Community 202 - "Oxlint Config"
Cohesion: 0.33
Nodes (5): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 203 - "Multi-Branch Build Order"
Cohesion: 0.40
Nodes (4): Safety-Net Build Order (Six Steps), Multi-Branch Number Maze, HMS/EMR Channel Discovery, Child 8: Multi-Branch / Fleet Deployment

### Community 213 - "VAD Fixture Pipeline Test"
Cohesion: 0.33
Nodes (4): generate(), generate_events(), synthesize_stream(), transcribe()

### Community 214 - "Local LLM Config"
Cohesion: 0.40
Nodes (5): llm_local, api_key, base_url, model, type

### Community 215 - "Monitoring Config Tests"
Cohesion: 0.40
Nodes (4): MonitoringConfig, test_monitoring_log_level_is_not_an_alias_for_the_default(), test_monitoring_nested_sections_are_typed(), test_monitoring_phi_masking_is_configurable_per_plan_t8()

## Ambiguous Edges - Review These
- `9 LLM tool functions list` → `LLM tool functions`  [AMBIGUOUS]
  MEMORY.md · relation: conceptually_related_to
- `Local mode hardware requirements` → `Fully local quick start`  [AMBIGUOUS]
  MEMORY.md · relation: conceptually_related_to
- `SHEFA medical voice agent` → `D11 demand proof gate`  [AMBIGUOUS]
  TODOS.md · relation: conceptually_related_to
- `Voice pipeline` → `console half-duplex microphone gate`  [AMBIGUOUS]
  src/shefa/static/console.html · relation: conceptually_related_to
- `Engineering Item Mapping E1-E12` → `Child 4: Test the Real Loop + Calibration + Uptime`  [AMBIGUOUS]
  docs/designs/shefa-spec-epic-plan.md · relation: conceptually_related_to
- `E4 Honest Forward Semantics + verified_rings` → `Child 2: Safety-Net Conversation`  [AMBIGUOUS]
  docs/designs/shefa-spec-epic-plan.md · relation: conceptually_related_to
- `Revision 1: Asterisk/FreeSWITCH + BD SIP Trunk` → `Approach B: Live-Trial Coverage Agent`  [AMBIGUOUS]
  docs/designs/shefa-safety-net-wedge.md · relation: conceptually_related_to
- `Piper bn_BD-google-medium` → `No Bengali entry in the official Piper voice list`  [AMBIGUOUS]
  docs/research/notes/tts.md · relation: conceptually_related_to
- `Piper bn_BD-google-medium` → `Bangla Piper voice bn_BD.nf_cycgan.onnx named blocker`  [AMBIGUOUS]
  docs/superpowers/specs/2026-10-01-shefa-owner-console.md · relation: conceptually_related_to
- `bangla-speech-processing VITS voices (female/male)` → `Local TTS research notes (Bangla + English)`  [AMBIGUOUS]
  docs/research/notes/tts.md · relation: references
- `Hybrid demo fallback (local ASR and Piper, cloud LLM)` → `Recommended free demo stack`  [AMBIGUOUS]
  docs/research/bangla-english-voice-models-2026-11.md · relation: conceptually_related_to
- `AudioSocket media bridge (8 kHz PCM over TCP, one connection per call)` → `SIP trunk and FreeSWITCH bridge unlanded`  [AMBIGUOUS]
  docs/superpowers/specs/2026-10-01-shefa-owner-console.md · relation: conceptually_related_to

## Knowledge Gaps
- **85 isolated node(s):** `shefa-medical-voice-agent`, `MUST_BE_FULLY_COVERED module set`, `CONVERGING_MODULES module set`, `Skill routing rules`, `BTRC-licensed SIP trunk` (+80 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1442 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **61 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AudioFrame` connect `Audio Frame Streaming` to `Threaded TTS Wrapper`, `Media Queue Concurrency`, `Scripted Voice Calls`, `AudioSocket Call Simulation`, `Failure Taxonomy Harness`, `Lab Dates and Scenarios`, `Twilio Media and Call Log`, `Voice Pipeline Streaming`, `Audio Codec Boundary`, `Model Registry and TTS`, `Base Model Contracts`, `Piper TTS Adapter`, `Outbound Reminder Pipeline`, `Mulaw Audio Conversion`, `Twilio Inbound Decoding`, `TTS Persistent Session`, `Media Queue Stall Tests`, `Speak-To Playback Tests`, `Pipeline Language Detection`, `Other-Language Routing Tests`, `Piper Stream Pump`, `Kokoro Local Voice`, `Twilio Stream Addressing`, `Asterisk Fake Pipeline`, `Console API Tests`, `Playback Resample Test`, `Playback Empty Result Test`, `Playback Encoding Test`, `Playback Dead Socket Test`, `Playback Exception Test`, `VAD Fixture Pipeline Test`, `Language-Routed TTS`, `Outbound Encode Tests`, `Audio Frame From Result`, `VAD Recording Sink`, `Twilio Helper Coverage`, `VITS TTS Adapter`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Are the 48 inferred relationships involving `AudioFrame` (e.g. with `run()` and `TTSResult`) actually correct?**
  _`AudioFrame` has 48 INFERRED edges - model-reasoned connections that need verification._
- **What connects `shefa-medical-voice-agent`, `MUST_BE_FULLY_COVERED module set`, `CONVERGING_MODULES module set` to the rest of the system?**
  _85 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Call Session Management` be split into smaller, more focused modules?**
  _Cohesion score 0.05526315789473684 - nodes in this community are weakly interconnected._
- **Why does `VoicePipeline` connect `Voice Pipeline Streaming` to `Call Session Management`, `FastAPI App and Calls`, `Reminders and Browser Calls`, `AudioSocket Call Simulation`, `Scripted Voice Calls`, `Failure Taxonomy Harness`, `Twilio Media and Call Log`, `Outbound Reminder Pipeline`, `Mulaw Audio Conversion`, `Speak-To Playback Tests`, `Pipeline Language Detection`, `Other-Language Routing Tests`, `Failure Taxonomy`, `Energy VAD`, `Text Chat Tests`, `Language Detector Tests`, `VAD Fixture Pipeline Test`, `Pipeline Helper Regression`, `VAD Audio Processing`, `Lab Execution`, `Pipeline Reply Generation`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `9 LLM tool functions list` and `LLM tool functions`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Local mode hardware requirements` and `Fully local quick start`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._