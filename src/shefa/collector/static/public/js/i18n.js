// Every user-visible string lives here, once in Bangla and once in English: D[key] = [bn, en].
// Elements made with T() remember their key, so switching language rewrites them in place and
// nothing (a recording in progress, a half-typed code) is lost by re-rendering.

const D = {
  brand: ["SHEFA কণ্ঠ", "SHEFA Voice"],
  other_lang: ["English", "বাংলা"],
  loading: ["একটু অপেক্ষা করুন…", "One moment…"],
  retry: ["আবার চেষ্টা করুন", "Try again"],
  back: ["পেছনে", "Back"],
  close: ["বন্ধ করুন", "Close"],
  copy: ["কপি", "Copy"],
  copied: ["কপি হয়েছে", "Copied"],
  copy_failed: ["কপি করা গেল না", "Could not copy"],
  server_down: ["সার্ভারে যাওয়া যাচ্ছে না। ইন্টারনেট দেখে আবার চেষ্টা করুন।", "Cannot reach the server. Check your internet and try again."],
  err_generic: ["কিছু একটা ভুল হয়েছে। আবার চেষ্টা করুন।", "Something went wrong. Please try again."],
  err_slow_down: ["এখন অনেক মানুষ একসাথে ঢুকছে। একটু পরে আবার চেষ্টা করুন।", "Many people are joining right now. Please try again in a little while."],
  err_challenge: ["যাচাই হয়নি। পেজটা রিলোড করে আবার চেষ্টা করুন।", "The check did not pass. Reload the page and try again."],
  err_consent: ["আগে সম্মতির ঘরে টিক দিন।", "Please tick the consent box first."],
  err_signed_out: ["আপনার সেশন শেষ হয়ে গেছে। পেজটা রিলোড করে আবার শুরু করুন।", "Your session ended. Reload the page and start again."],
  err_too_big: ["রেকর্ডিংটা অনেক বড়, ছোট করে আবার বলুন।", "That recording is too large. Please say it shorter."],
  err_daily_cap: ["আজকের জন্য অনেক হয়েছে, ধন্যবাদ! কাল আবার আসুন।", "That is plenty for today, thank you! Come back tomorrow."],
  err_paused: ["আজ একটু বিশ্রামে। রেকর্ডিং ফোনে জমা আছে, পরে নিজেই চলে যাবে।", "Resting today. Your recordings wait on your phone and will go later."],
  err_net_wait: ["ইন্টারনেট নেই। রেকর্ডিং ফোনে জমা আছে।", "No internet. Your recordings are saved on the phone."],

  // queue bar
  q_bar: ["ফোনে সেভ হয়েছে · {n} টি পাঠানো বাকি", "Saved on your phone · {n} left to send"],
  q_bar_zero: ["ফোনে সেভ হয়েছে · সব পাঠানো হয়েছে", "Saved on your phone · all sent"],
  q_leave: ["রেকর্ডিং এখনো পাঠানো হয়নি। পেজ ছাড়বেন?", "Recordings are still waiting to send. Leave the page?"],

  // landing
  sent_by: ["{name} পাঠিয়েছে", "Sent by {name}"],
  hero_title: ["বাংলা ভয়েস সহকারী শেখান", "Teach Bangla voice assistants"],
  hero_sub: ["হাসপাতাল বা ইন্টারনেট সেবায় ফোন করার মতো করে কিছু প্রশ্নের উত্তর নিজের ভাষায় বলুন। ১০ মিনিটেই হয়ে যায়।", "Answer a few questions as if you were phoning a hospital or an internet provider, in your own words. It takes 10 minutes."],
  voice_note: ["ভয়েস মেসেজ শুনুন", "Listen to a voice note"],
  voice_note_from: ["{name}-এর ভয়েস মেসেজ শুনুন", "Listen to the voice note from {name}"],
  c1: ["আপনার কণ্ঠ রেকর্ড হবে, এই প্রকল্পের বাংলা ভয়েস সহকারীদের (যেমন SHEFA) শেখাতে ব্যবহার হবে", "Your voice is recorded and used to teach this project's Bangla voice assistants (such as SHEFA)"],
  c2: ["আসল নাম বা ফোন নম্বর বলবেন না, কাল্পনিক নামই ঠিক আছে", "Do not say your real name or number; a made-up name is fine"],
  c3: ["চাইলে যেকোনো সময় ডিলিট কোড দিয়ে মুছে ফেলতে পারবেন", "You can delete your recordings any time with your delete code"],
  tick: ["১৮+, আমার কণ্ঠ ব্যবহারে রাজি", "I am 18+ and I agree to my voice being used"],
  tick_back: ["আপনি আগেই রাজি হয়েছেন", "You have already agreed"],
  more: ["আরও জানুন", "Learn more"],
  start: ["শুরু", "Start"],
  friend: ["বন্ধুর সাথে", "With a friend"],
  delete_link: ["আমার রেকর্ডিং মুছুন", "Delete my recordings"],
  maint: ["আজ একটু বিশ্রামে। আপনি রেকর্ড করতে পারেন, ফোনে জমা থাকবে, পরে নিজেই চলে যাবে।", "We are resting today. You can still record: clips wait on your phone and go later."],
  inapp_title: ["Chrome-এ খুলুন", "Open in Chrome"],
  inapp_body: ["এই অ্যাপের ভেতরে মাইক চালু নাও হতে পারে। নিচের বোতাম চাপুন, অথবা লিংক কপি করে Chrome বা Safari-তে দিন।", "The microphone may not work inside this app. Tap the button below, or copy the link and open it in Chrome or Safari."],
  inapp_copy: ["লিংক কপি করুন", "Copy link"],
  inapp_go: ["তবুও এখানেই চালাই", "Continue here anyway"],
  invited: ["বন্ধু আপনাকে ডেকেছে। কোড: {code}", "A friend invited you. Code: {code}"],

  // mic check
  mc_title: ["আগে মাইক দেখে নিই", "Let us check your microphone first"],
  mc_sub: ["বোতাম চেপে একটা বাক্য বলুন, যেমন “আমি ডাক্তার দেখাতে চাই।” এটা কোথাও পাঠানো হবে না।", "Tap the button and say a sentence, like “I want to see a doctor.” This is not sent anywhere."],
  mc_tip: ["শান্ত জায়গায় যান। ব্লুটুথ ইয়ারফোন বা হেডফোন খুলে রাখুন, ফোনের নিজের মাইকই ভালো।", "Find a quiet spot. Take off Bluetooth earphones or headphones: the phone's own mic works best."],
  mc_go: ["মাইক চালু করে বলুন", "Turn on the mic and speak"],
  mc_done: ["বলা হয়েছে", "Done speaking"],
  mc_listening: ["শুনছি… বলুন", "Listening… speak now"],
  mc_good: ["ভালো! আপনার গলা পরিষ্কার শোনা যাচ্ছে।", "Good! Your voice comes through clearly."],
  mc_quiet: ["প্রায় কিছুই শোনা যায়নি। মাইকের কাছে মুখ এনে আবার বলুন।", "We hardly heard you. Bring the phone closer and try again."],
  mc_noisy: ["আশেপাশে একটু গোলমাল আছে। পারলে শান্ত জায়গায় যান।", "It is a bit noisy around you. Move somewhere quieter if you can."],
  mc_next: ["ঠিক আছে, এগোই", "Okay, continue"],
  mc_again: ["আবার দেখি", "Check again"],
  mic_denied: ["মাইকের অনুমতি পাওয়া যায়নি। ব্রাউজারের সেটিং থেকে মাইক চালু করে আবার চেষ্টা করুন।", "Microphone permission was not given. Allow the microphone in your browser settings and try again."],
  mic_none: ["এই ফোনে মাইক পাওয়া যায়নি।", "No microphone was found on this phone."],
  mic_busy: ["মাইক অন্য কোনো অ্যাপ ব্যবহার করছে। সেটা বন্ধ করে আবার চেষ্টা করুন।", "Another app is using the microphone. Close it and try again."],
  mic_insecure: ["এই লিংকে মাইক চলবে না। https লিংক ব্যবহার করুন।", "The microphone does not work on this link. Use the https link."],
  mic_generic: ["মাইক চালু করা গেল না। পেজটা রিলোড করে আবার চেষ্টা করুন।", "Could not start the microphone. Reload the page and try again."],

  // settings
  set_ask: ["আপনি এখন কোথায়?", "Where are you right now?"],
  set_here: ["জায়গা: {name}", "Place: {name}"],
  set_change: ["বদলান", "Change"],
  set_home: ["ঘরে, শান্ত", "At home, quiet"],
  set_street: ["রাস্তায় বা বাজারে", "Street or market"],
  set_fan: ["ফ্যান বা টিভি চলছে", "Fan or TV on"],
  set_office: ["অফিস বা দোকানে", "Office or shop"],
  set_vehicle: ["গাড়ি বা রিকশায়", "Car or rickshaw"],

  // answer the agent
  counter: ["{n} টি রেকর্ডিং", "{n} recorded"],
  step_of: ["ধাপ {i} / {n}", "Step {i} of {n}"],
  sit_title: ["পরিস্থিতি", "The situation"],
  persona: ["কাল্পনিক নাম: {name}। এই নামটাই বলুন।", "Made-up name: {name}. Use this one."],
  agent_says: ["সহকারী বলছে", "The assistant says"],
  agent_hearing: ["শুনুন…", "Listen…"],
  agent_replay: ["আবার শুনুন", "Listen again"],
  agent_play: ["চালান", "Play"],
  agent_text: ["লেখাটা দেখুন", "Show the text"],
  hint_title: ["আপনি যা বলতে চান", "What you want to say"],
  nudge: ["নিজের মতো করে বলুন। লেখা পড়ে শোনাবেন না।", "Say it in your own words. Do not read it out."],
  rec_wait: ["সহকারীর কথা শেষ হলে বোতাম চালু হবে", "The button turns on when the assistant finishes"],
  rec_tap: ["ট্যাপ করে বলুন", "Tap and speak"],
  rec_stop: ["বলা হলে ট্যাপ করুন", "Tap when you are done"],
  rec_left: ["{s} সেকেন্ড বাকি", "{s} seconds left"],
  rec_hear: ["শুনে দেখুন", "Listen back"],
  rec_ok: ["ঠিক আছে", "That is good"],
  rec_again: ["আবার", "Again"],
  rec_sending: ["পাঠানো হচ্ছে…", "Sending…"],
  rec_saved: ["ফোনে সেভ হয়েছে", "Saved on your phone"],
  rec_quiet: ["কথা খুব আস্তে ছিল। আবার বলা ভালো।", "That was very quiet. It is better to say it again."],
  rec_short: ["খুব ছোট হয়েছে, একটু বেশি বলুন।", "That was too short. Please say a bit more."],
  rec_redo: ["এই ধাপটা আবার বলুন।", "Please say this step again."],
  rec_late: ["একটা রেকর্ডিং নেওয়া যায়নি: {msg}", "One recording was not accepted: {msg}"],
  rec_redo_btn: ["আবার বলি", "Say it again"],
  skip_step: ["এই ধাপ বাদ দিই", "Skip this step"],
  skip_card: ["অন্য কার্ড দিন", "Give me another card"],
  card_done: ["দারুণ হয়েছে!", "Well done!"],
  card_done_n: ["এই কার্ডে {n} টি রেকর্ডিং হলো।", "{n} recordings on this card."],
  card_more: ["আরও কয়েকটা দিলে SHEFA আরও ভালো শিখবে। তবে আপনার ইচ্ছা।", "A few more would help SHEFA learn. But it is up to you."],
  more_card: ["আরও একটা কার্ড", "One more card"],
  finish: ["শেষ করি", "I am finished"],
  // version 2: a call to the front desk
  desk_label: ["ফ্রন্ট ডেস্ক", "Front desk"],
  desk_speaking: ["ফ্রন্ট ডেস্ক বলছেন… শুনুন", "The front desk is speaking… listen"],
  desk_tap: ["ফ্রন্ট ডেস্কের কথা শুনতে \"আবার শুনুন\" চাপুন, অথবা লেখাটা পড়ে নিন", "Tap \"Listen again\" to hear the front desk, or read the words"],
  your_turn: ["এবার আপনি বলুন", "Now it is your turn to speak"],
  call_ending: ["ফ্রন্ট ডেস্ক কল শেষ করছেন", "The front desk is ending the call"],
  hint_title2: ["আপনি যা বলবেন (নিজের ভাষায়)", "What you say (in your own words)"],
  fork_ask: ["কী বলতে চান? একটা বেছে নিন", "What do you want to say? Pick one"],
  pick_patient: ["{who} কে?", "Who is the {who}?"],
  pick_patient_sub: ["আপনার সাথে যেটা মেলে সেটা বেছে নিন। পুরো কলে এই নাম আর বয়সই বলবেন।", "Pick the one that fits you. Use this name and age for the whole call."],
  age_years: ["{age} বছর", "{age} years"],
  patient_line: ["{who}: {rel} {name}, {age} বছর", "{who}: {rel} {name}, {age} years"],
  turn_n: ["কথা {n}", "Turn {n}"],
  history: ["এ পর্যন্ত কথা", "The call so far"],
  you_done: ["আপনি: ✓ বলা হয়েছে", "You: ✓ recorded"],
  you_skipped: ["আপনি: (বাদ দিয়েছেন)", "You: (skipped)"],
  skip_call: ["অন্য কল দিন", "Give me another call"],
  call_done: ["কল শেষ!", "Call finished!"],
  call_done_n: ["এই কলে {n} টি রেকর্ডিং হলো। ধন্যবাদ!", "{n} recordings in this call. Thank you!"],
  more_call: ["আরেকটা কল করি", "Make another call"],
  rec_cut: ["সময় শেষ হয়ে কথা কেটে গেছে। একটু ছোট করে আবার বলুন।", "Time ran out and the end was cut off. Please say it again, a little shorter."],
  rec_keep_cut: ["যেমন আছে রাখুন", "Keep it as it is"],
  rm_end: ["কল শেষ করি", "End the call"],
  dl_skip: ["বলব না", "Prefer not to say"],
  dl_other: ["অন্য", "Other"],
  dl_mymensingh: ["ময়মনসিংহের", "Mymensingh"],
  dl_rangpur: ["রংপুরের", "Rangpur"],
  dl_rajshahi: ["রাজশাহীর", "Rajshahi"],
  dl_khulna: ["খুলনা-যশোরের", "Khulna/Jashore"],
  dl_barishal: ["বরিশালের", "Barishal"],
  dl_cumilla: ["কুমিল্লার", "Cumilla"],
  dl_noakhali: ["নোয়াখালীর", "Noakhali"],
  dl_sylhet: ["সিলেটি", "Sylheti"],
  dl_chattogram: ["চাটগাঁইয়া", "Chattogram"],
  dl_dhaka: ["ঢাকাইয়া", "Dhaka"],
  dl_standard: ["প্রমিত", "Standard"],
  opt_dialect: ["বাড়িতে কোন আঞ্চলিক টানে কথা বলেন", "Which regional way of speaking do you use at home"],
  topic_isp: ["ইন্টারনেট সেবা", "Internet provider"],
  topic_hospital: ["হাসপাতাল", "Hospital"],
  topic_any: ["যেকোনো", "Any"],
  topic_title: ["কোন ধরনের কল করবেন?", "What kind of calls?"],
  reconsent_sub: ["এখন ইন্টারনেট সেবার কলও আছে, আর রেকর্ডিং এই প্রকল্পের অন্য বাংলা ভয়েস সহকারী শেখাতেও লাগবে। পড়ে আবার টিক দিন।", "There are now internet-provider calls too, and recordings also teach this project's other Bangla voice assistants. Please read and tick again."],
  reconsent_title: ["সম্মতির কথা একটু বদলেছে", "The consent has changed a little"],
  share_tick: ["(ঐচ্ছিক) অন্য প্রতিষ্ঠানের সাথে শেয়ার বা লাইসেন্স করাতেও রাজি", "(Optional) I also agree to sharing or licensing to other organisations"],
  free_title: ["এই কলটা নিজের মতো করে", "This call is in your own words"],
  free_intro: ["এবার কোনো লেখা দেখানো হবে না। সত্যিকারের ফোনকলে যা বলতেন, তাই বলুন।", "No wording this time. Say what you would say on a real call."],
  free_phone: ["নম্বর চাইলে বলবেন: {phone}", "If asked for a number, give: {phone}"],
  free_hint: ["নিজের মতো করে উত্তর দিন।", "Answer in your own way."],
  free_fork: ["যেটা বেছে নিয়েছেন, সেটা নিজের মতো করে বলুন।", "Say what you picked, in your own way."],
  nudge_pass: ["আপনি {n} টা রেকর্ডিং দিয়েছেন, অনেক ধন্যবাদ! একজনের কণ্ঠ বেশি হলে মডেল শুধু সেই কণ্ঠই চিনতে শেখে। এবার পরিবারের বা আশেপাশের অন্য কাউকে দিন?", "You have given {n} recordings, thank you! If one voice dominates, the model learns only that voice. Hand the phone to someone else now?"],
  nudge_pass_btn: ["পরের জনকে দিই", "Hand it to the next person"],
  noisy_ask: ["পরের কলটা একটু আওয়াজের মধ্যে করবেন? রাস্তা, বাজার, গাড়ি, বা ফ্যান-টিভি চালু রেখে। আসল ফোনকল এমন জায়গা থেকেই আসে। জায়গা বদলালে নিচে বেছে নিন।", "Could you make the next call somewhere noisier? A road, a bazaar, a vehicle, or with a fan or TV on. Real calls come from places like that. Pick the new place below."],
  noisy_progress: ["সবাই মিলে আওয়াজের মধ্যে: {m} / {goal} মিনিট", "Everyone together, with background noise: {m} / {goal} minutes"],
  rm_desk_say: ["এবার আপনি বলুন (নিজের ভাষায়, পেশাদারভাবে)", "Your turn (in your own words, professionally)"],
  rm_desk_rule: ["যিনি ফোন করেছেন তিনি যা জিজ্ঞেস করবেন শুধু তার উত্তর দিন, আর কাজের জন্য দরকারি তথ্য নিন। নিজে থেকে কথা বাড়াবেন না।", "Answer only what the caller asks and take what the task needs. Do not extend the call yourself."],
  rm_desk_last: ["এটাই কলের শেষ কথা।", "This is the last line of the call."],
  rm_desk_said: ["ফ্রন্ট ডেস্ক মোটামুটি এটা বলেছেন", "Roughly what the front desk said"],
  cards_fail: ["নতুন কার্ড আনা যাচ্ছে না।", "Could not get a new card."],

  rej_too_short: ["খুব ছোট রেকর্ডিং, আবার বলুন।", "That was too short. Please say it again."],
  rej_too_long: ["রেকর্ডিং বেশি লম্বা, ছোট করে আবার বলুন।", "That was too long. Please say it shorter."],
  rej_silent: ["কথা শোনা যায়নি, ফোনের কাছে এসে আবার বলুন।", "We could not hear you. Come closer to the phone and try again."],
  rej_clipped: ["আওয়াজ ফেটে গেছে, একটু আস্তে বা দূরে থেকে বলুন।", "The sound was too loud. Speak a little softer or further away."],
  rej_unreadable: ["রেকর্ডিং পড়া যায়নি, আবার চেষ্টা করুন।", "We could not read that recording. Please try again."],
  rej_too_big: ["রেকর্ডিংটা অনেক বড়, ছোট করে আবার বলুন।", "That recording is too large. Please say it shorter."],

  // pass the phone
  pass_title: ["ফোনটা পরের জনকে দিন", "Hand the phone to the next person"],
  pass_sub: ["উনি নিজের কণ্ঠে বলবেন। ১৮+ হলে এবং রাজি থাকলে টিক দিন।", "They will speak in their own voice. Tick if they are 18+ and agree."],
  next_person: ["পরের জন", "Next person"],

  // thank you
  th_title: ["ধন্যবাদ!", "Thank you!"],
  th_sum: ["আপনি {n} টি বাক্য দিয়েছেন, প্রায় {m} মিনিট।", "You gave {n} sentences, about {m} minutes."],
  th_sum_none: ["এখনো কোনো রেকর্ডিং হয়নি। চাইলে এখনই শুরু করতে পারেন।", "Nothing recorded yet. You can start whenever you like."],
  th_wait: ["পেজটা খোলা রাখুন, {n} টি পাঠানো বাকি", "Keep this page open, {n} left to send"],
  th_alldone: ["সব রেকর্ডিং পৌঁছে গেছে।", "All your recordings have arrived."],
  group_title: ["সবার মিলিত লক্ষ্য", "Everyone together"],
  group_line: ["{m} / {g} মিনিট, {s} জন", "{m} of {g} minutes, {s} people"],
  code_title: ["আপনার ডিলিট কোড", "Your delete code"],
  code_note: ["এই কোডটা রাখুন, চাইলে রেকর্ডিং মুছতে পারবেন।", "Keep this code. You can use it to delete your recordings."],
  opt_title: ["চাইলে আরও দুটো কথা (না দিলেও চলবে)", "If you like, two more things (optional)"],
  opt_age: ["বয়স", "Age"],
  opt_gender: ["লিঙ্গ", "Gender"],
  opt_div: ["কোন বিভাগে থাকেন", "Which division do you live in"],
  opt_nick: ["ডাকনাম (ইচ্ছা হলে)", "Nickname (optional)"],
  opt_credit: ["নামটা ধন্যবাদ তালিকায় দেখান", "Show this name on the thank-you list"],
  opt_save: ["পাঠান", "Send"],
  opt_saved: ["পাঠানো হয়েছে, ধন্যবাদ।", "Sent, thank you."],
  g_female: ["নারী", "Female"], g_male: ["পুরুষ", "Male"], g_other: ["অন্য", "Other"], g_skip: ["বলতে চাই না", "Prefer not to say"],
  d_dhaka: ["ঢাকা", "Dhaka"], d_chattogram: ["চট্টগ্রাম", "Chattogram"], d_rajshahi: ["রাজশাহী", "Rajshahi"],
  d_khulna: ["খুলনা", "Khulna"], d_barishal: ["বরিশাল", "Barishal"], d_sylhet: ["সিলেট", "Sylhet"],
  d_rangpur: ["রংপুর", "Rangpur"], d_mymensingh: ["ময়মনসিংহ", "Mymensingh"], d_abroad: ["বিদেশ", "Abroad"], d_skip: ["বলতে চাই না", "Prefer not to say"],
  share_title: ["বন্ধুদেরও বলুন", "Tell your friends"],
  share_wa: ["WhatsApp-এ পাঠান", "Send on WhatsApp"],
  share_link: ["লিংক কপি", "Copy link"],
  share_img: ["ছবি শেয়ার করুন", "Share a picture"],
  share_dl: ["ছবি নামান", "Download the picture"],
  wa_text: ["আমি SHEFA-কে বাংলা শেখাতে ১০ মিনিট দিলাম। আপনিও পারবেন: {url}", "I spent 10 minutes teaching SHEFA Bangla. You can too: {url}"],
  img_main: ["আমি {n} টা বাক্য দিয়ে SHEFA-কে বাংলা শেখালাম", "I taught SHEFA Bangla with {n} sentences"],
  img_sub: ["আপনিও পারবেন", "You can too"],
  more_rec: ["আরও রেকর্ড করি", "Record more"],

  // delete page
  del_title: ["আমার রেকর্ডিং মুছুন", "Delete my recordings"],
  del_sub: ["আপনার ডিলিট কোডটা লিখুন, যেমন AB12-CD34-EF56।", "Type your delete code, like AB12-CD34-EF56."],
  del_label: ["ডিলিট কোড", "Delete code"],
  del_btn: ["মুছে ফেলুন", "Delete"],
  del_sure: ["হ্যাঁ, সব মুছে ফেলুন", "Yes, delete everything"],
  del_warn: ["মুছলে আর ফেরানো যাবে না।", "This cannot be undone."],
  del_ok: ["{n} টি রেকর্ডিং মুছে ফেলা হয়েছে।", "{n} recordings were deleted."],
  del_nf: ["এই কোড পাওয়া যায়নি। আবার দেখে লিখুন।", "That code was not found. Please check it."],

  // call a friend
  rm_title: ["বন্ধুর সাথে", "With a friend"],
  rm_sub: ["একজন রোগীর পরিবার হয়ে ফোন করবেন, আরেকজন ক্লিনিকের রিসেপশনে। আলাদা ফোনে পালা করে বলবেন। লাইভ কথা নয়, রেকর্ড করে পাঠানো।", "One of you calls like a patient's family, the other is the clinic desk. On two phones, take turns. Not a live call: you record and send."],
  rm_make: ["আমি ফোন করছি (ঘর বানাই)", "I am the caller (make a room)"],
  rm_join: ["আমি রিসেপশনে (কোড দিয়ে ঢুকি)", "I am the desk (join with a code)"],
  rm_code_label: ["৬ অক্ষরের কোড", "6-letter code"],
  rm_go: ["ঢুকি", "Join"],
  rm_no_room: ["এই কোডে কোনো ঘর নেই।", "There is no room with this code."],
  rm_full: ["এই ঘরে আগেই দুজন আছে।", "This room already has two people."],
  rm_code_is: ["আপনার ঘরের কোড", "Your room code"],
  rm_wait: ["বন্ধু ঢুকলে নিজে থেকেই শুরু হবে। কোড বা লিংক পাঠান।", "It starts by itself when your friend joins. Send the code or the link."],
  rm_alone: ["একা করি", "Do it alone"],
  rm_alone_hint: ["বন্ধু আসেনি? সহকারীর রেকর্ড করা প্রশ্ন শুনে একাই করতে পারেন।", "No friend yet? Answer the assistant's recorded questions on your own."],
  rm_invite: ["বন্ধুর সাথে ক্লিনিকে ফোন-ফোন খেলি! কোড: {code} {url}", "Let us practise a clinic call together! Code: {code} {url}"],
  rm_caller: ["আপনি ফোন করছেন", "You are the one calling"],
  rm_desk: ["আপনি ফোন ধরছেন (রিসেপশন বা কাস্টমার কেয়ার)", "You answer the phone (front desk or customer care)"],
  rm_turn_you: ["আপনার পালা", "Your turn"],
  rm_turn_wait: ["বন্ধুর পালা। একটু অপেক্ষা করুন…", "Your friend's turn. Please wait…"],
  rm_turn_first: ["রিসেপশন আগে ফোন ধরবে। একটু অপেক্ষা করুন…", "The desk picks up first. Please wait…"],
  rm_hear: ["বন্ধু যা বলেছে শুনুন", "Hear what your friend said"],
  rm_hear_loading: ["আনা হচ্ছে…", "Loading…"],
  rm_ask: ["রোগীর কথা শুনে উত্তর দিন বা পরের প্রশ্নটা করুন (নিচের তালিকা দেখে)।", "Answer the caller or ask the next question (use the sheet below)."],
  rm_open: ["ফোন ধরে সালাম দিন, ক্লিনিকের নাম বলুন, তারপর জিজ্ঞেস করুন কীভাবে সাহায্য করতে পারেন।", "Pick up, say salam and the clinic's name, then ask how you can help."],
  rm_done: ["দুজনের কথা শেষ! ধন্যবাদ।", "The call is finished! Thank you."],
  rm_sheet: ["ক্লিনিকের তালিকা", "Clinic sheet"],
  rm_fee: ["ফি", "Fee"],
  rm_room: ["রুম", "Room"],
};

let lang = "bn";
try { lang = localStorage.getItem("shefa.lang") || "bn"; } catch { /* no storage */ }
if (lang !== "en") lang = "bn";

const listeners = new Set();
export const getLang = () => lang;
export const onLang = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

// Bangla digits for Bangla text; English keeps 0-9.
export function n(x) {
  const s = String(x);
  return lang === "bn" ? s.replace(/\d/g, (d) => "০১২৩৪৫৬৭৮৯"[d]) : s;
}

export function t(key, p) {
  const row = D[key];
  if (!row) return key;
  return row[lang === "bn" ? 0 : 1].replace(/\{(\w+)\}/g, (_, k) => {
    const v = p && p[k];
    return typeof v === "number" ? n(v) : v == null ? "" : v;
  });
}

// The server only gives Bangla labels for settings; English comes from our own table.
// The words to show a person when the server turned their clip down.
export function rejectionText(reason, fallback) {
  return D["rej_" + reason] ? t("rej_" + reason) : fallback || t("err_generic");
}

export function settingName(s) {
  return lang === "en" && D["set_" + s.id] ? D["set_" + s.id][1] : s.bn;
}

function paint(el) {
  el.textContent = t(el.dataset.k, el._p);
}

// An element whose text follows the language: T("start") or T("th_wait", {n: 3}, "p").
export function T(key, params, tag = "span") {
  const el = document.createElement(tag);
  el.dataset.k = key;
  el._p = params;
  paint(el);
  return el;
}

// Change the key or numbers of a T() element later (counters, countdowns).
export function setT(el, key, params) {
  el.dataset.k = key;
  el._p = params;
  paint(el);
}

// Same idea for attributes such as aria-label or placeholder.
export function attrT(el, attr, key) {
  el.dataset.ka = attr + ":" + key;
  el.setAttribute(attr, t(key));
  return el;
}

export function setLang(next) {
  lang = next === "en" ? "en" : "bn";
  try { localStorage.setItem("shefa.lang", lang); } catch { /* ignore */ }
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-k]").forEach(paint);
  document.querySelectorAll("[data-ka]").forEach((el) => {
    const [attr, key] = el.dataset.ka.split(":");
    el.setAttribute(attr, t(key));
  });
  listeners.forEach((fn) => fn(lang));
}

document.documentElement.lang = lang;
