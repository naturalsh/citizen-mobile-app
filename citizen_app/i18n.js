/* Every word the citizen reads, in English, Turkish and Greek, and how numbers, distances and dates are written.
   A text is asked for by its key: t('verdict.blocked', {m: '120 m'}). A key missing in a language falls back to English.

   The Turkish and Greek wording was written by the team, not by a professional translator: it has to be read by a
   native speaker who knows how AFAD words things before any real use. */

export const LANGUAGES = {en: 'English', tr: 'Türkçe', el: 'Ελληνικά'};

const TEXT = {
    en: {
        appName: 'Safe places',
        exercise: 'EXERCISE',
        exerciseShort: 'Not a real emergency',
        exerciseTitle: 'This is an exercise',
        simulated: 'Some streets carry simulated events, made for this demonstration.',
        call: 'Call 112',
        language: 'Language',
        about: 'About and legend',
        close: 'Close',
        loading: 'Loading the area…',
        noPack: 'No connection, and nothing is saved on this phone yet.',
        tooOld: 'This page is older than the information it received. Reload it.',
        openGround: 'Go to open ground, away from buildings, walls and power lines. In danger call 112.',
        retry: 'Try again',
        notice: 'Notice',
        whereTitle: 'Where are you?',
        whereClosest: 'Where is closest to you?',
        wherePrivate: 'Your position stays on this phone. It is never sent anywhere.',
        useGps: 'Use my location',
        chooseOnMap: 'Choose on the map',
        example: 'Example position',
        tapHint: 'Tap the map where you are.',
        cancel: 'Cancel',
        gpsWaiting: 'Finding your location…',
        gpsDenied: 'The phone did not share its location. Choose your position on the map.',
        gpsFailed: 'Your location could not be found. Choose your position on the map.',
        gpsOutside: 'You are {km} from {area}. This prototype covers only that area. To try it, choose a position on the map.',
        noStreet: 'No street of this map is within {m} of that point. Choose a point nearer to a street.',
        you: 'You are here. Drag to move.',
        position: 'Your position',
        fromGps: 'from the phone, ± {m}',
        fromTap: 'chosen on the map',
        fromExample: 'example position',
        change: 'Change',
        assembly: 'Assembly points',
        medical: 'Hospitals',
        noAssembly: 'No assembly point is listed for this area yet.',
        noMedical: 'No hospital is listed for this area.',
        allReported: 'Every place in this list was reported full or closed.',
        allReportedShort: 'All reported full or closed',
        urgent: 'In an emergency call 112.',
        suggested: 'Suggested',
        walk: '~{min} walk ({m})',
        eta: 'Est. arrival {when}',
        minutes: '{n} min',
        noRoute: 'No walking route found on this map.',
        kind: {assembly_point: 'Assembly point', shelter: 'Shelter', hospital: 'Hospital', clinic: 'Health centre'},
        facility: {water: 'Water', medical: 'First aid', power: 'Power / charging', shelter: 'Tents / shelter', accessible: 'Accessible'},
        facilitiesLabel: 'Available facilities',
        official: 'Official list',
        unofficial: 'Not from an official list',
        emergencyYes: 'Emergency department',
        emergencyNo: 'No emergency department',
        source: 'Source: {source}. Compared with it on {date}.',
        report: {in_use: 'In use: it takes people in.', full: 'Full: it takes nobody more. Go to another place.', closed: 'Closed: do not go there.',
                 none: 'Nobody has reported yet whether this place is in use.'},
        reportedAt: 'Reported by the operations room: {when}.',
        reportShort: {in_use: 'In use', full: 'Full', closed: 'Closed'},
        group: {checked: 'Confirmed passable', unchecked: 'Not confirmed yet', no_data: 'No information', blocked: 'Reported blocked'},
        groupMore: {
            checked: 'an operator looked at the drone photo and confirmed it',
            unchecked: 'the drone found no blockage, but no operator has looked yet',
            no_data: 'outside the drone flight, or the drone could not see it',
            blocked: 'less than 2 m free. Avoid it',
        },
        verdict: {
            checked: 'Every street on this route was confirmed passable by an operator.',
            partly: '{m} of this route are not confirmed. Watch the street as you go.',
            blocked: 'This route crosses {m} reported blocked. Go only if you can see that you can pass. If not, stay on open ground away from buildings and call 112.',
        },
        trust: 'The map can be wrong or out of date. Trust what you see, and follow official instructions first.',
        steps: 'Step by step',
        step: {start: 'Start on {name}', straight: 'Continue on {name}', left: 'Turn left onto {name}', right: 'Turn right onto {name}',
               toStreet: 'Walk {m} to the street', arrive: 'Arrive: {name}', fromStreet: 'about {m} from the street'},
        unnamed: {street: 'a street without a name', footway: 'a footpath', steps: 'stairs', track: 'a track'},
        others: 'Other places',
        showAll: 'Show all ({n})',
        legendRoute: 'Your route',
        legendDrone: 'Area the drone photographed',
        legendOff: 'A place reported full or closed',
        droneLabel: 'Drone flight, {date}',
        seen: {drone: 'Seen by the drone on {date}.', field_report: 'Reported from the field on {date}.'},
        confirmedOn: 'Confirmed by an operator on {date}.',
        notConfirmed: 'No operator has confirmed it yet.',
        width: 'About {m} m free.',
        narrow: 'Narrow for vehicles (2 to 3 m), fine on foot.',
        simulatedEvent: 'Simulated event (demonstration).',
        received: 'Last information received: {when}.',
        ago: {now: 'just now', min: '{n} min ago'},
        offline: 'No connection. Showing the last information received ({when}).',
        updated: 'New information.',
        noticeNew: 'New notice at the top of the page.',
        noticeGone: 'The notice was withdrawn.',
        reportGone: 'report withdrawn',
        updatedPlaces: 'Places with a changed report: {n}.',
        updatedStreets: 'Streets changed: {n}.',
        routeChanged: 'Your way has changed.',
        routeSame: 'Your way stays the same.',
        mapMissing: 'This phone cannot draw the map. The list and the steps still work.',
        aboutWhat: 'Shows assembly points and hospitals, and a walking route that avoids streets reported blocked. A street is shown as passable only after an operator in the operations room looked at the drone photo and confirmed it.',
        aboutPrivacy: 'Privacy: the app downloads the same file for everybody and finds the route on your phone. Your position is not sent and not stored. No account, no cookies, no tracking.',
        aboutLimits: 'Limits: outside the drone flight nothing is known about the streets. Places come from the sources shown with each of them. Whether a place is in use now is known only where the operations room reported it. Official orders always come first.',
        keptLanguage: 'This phone keeps the language of the app.',
        keptPack: 'It keeps the last information it received, and shows it when there is no connection.',
        keptApp: 'It keeps the app itself, so that the app opens without a connection.',
        aboutPrototype: 'A prototype by team Nature Shield (Greece × Türkiye hackathon). Not an official service.',
        data: 'Data',
        legend: 'What the map shows',
        places: 'Places',
        showDetails: 'Details',
        showMap: 'Map',
        chooseFirst: 'Say where you are to see the way there.',
        openSource: 'Open the source',
        phone: 'Phone',
        mobileView: 'Mobile view',
        desktopView: 'Desktop view',
        locateMe: 'Find my location',
        recenterMap: 'Show full route',
        installApp: 'Install app',
        installTip: 'Add to your phone: in Safari tap Share → Add to Home Screen; in Chrome tap Install app.',
        navMap: 'Map',
        navAssembly: 'Assembly',
        navMedical: 'Hospitals',
        voiceTitle: '112 Voice Agent',
        voiceConnecting: 'Connecting to 112 agent…',
        voiceListening: 'Connected · Listening…',
        voiceSpeaking: 'Agent speaking…',
        voiceEnded: 'Call ended',
        voiceError: 'Could not connect to voice agent. Make sure the Voice_Agents backend is running.',
        voiceMute: 'Mute',
        voiceUnmute: 'Unmute',
        voiceEnd: 'End call',
        voiceDial112: 'Dial 112',
    },

    tr: {
        appName: 'Güvenli yerler',
        exercise: 'TATBİKAT',
        exerciseShort: 'Gerçek bir acil durum değildir',
        exerciseTitle: 'Bu bir tatbikattır',
        simulated: 'Bazı sokaklarda bu gösterim için hazırlanmış simülasyon olayları vardır.',
        call: '112\'yi ara',
        language: 'Dil',
        about: 'Hakkında ve renkler',
        close: 'Kapat',
        loading: 'Bölge yükleniyor…',
        noPack: 'Bağlantı yok ve bu telefonda henüz kayıtlı bilgi yok.',
        tooOld: 'Bu sayfa, aldığı bilgiden daha eski. Sayfayı yenileyin.',
        openGround: 'Binalardan, duvarlardan ve elektrik hatlarından uzak, açık bir alana gidin. Tehlikede 112\'yi arayın.',
        retry: 'Tekrar dene',
        notice: 'Duyuru',
        whereTitle: 'Neredesiniz?',
        whereClosest: 'Size en yakın yer neresi?',
        wherePrivate: 'Konumunuz bu telefonda kalır. Hiçbir yere gönderilmez.',
        useGps: 'Konumumu kullan',
        chooseOnMap: 'Haritadan seç',
        example: 'Örnek konum',
        tapHint: 'Haritada bulunduğunuz yere dokunun.',
        cancel: 'Vazgeç',
        gpsWaiting: 'Konumunuz bulunuyor…',
        gpsDenied: 'Telefon konumunu paylaşmadı. Konumunuzu haritadan seçin.',
        gpsFailed: 'Konumunuz bulunamadı. Konumunuzu haritadan seçin.',
        gpsOutside: '{area} bölgesine {km} uzaktasınız. Bu prototip yalnızca o bölgeyi kapsar. Denemek için haritadan bir konum seçin.',
        noStreet: 'Bu noktanın {m} yakınında haritada sokak yok. Bir sokağa daha yakın bir nokta seçin.',
        you: 'Buradasınız. Taşımak için sürükleyin.',
        position: 'Konumunuz',
        fromGps: 'telefondan, ± {m}',
        fromTap: 'haritadan seçildi',
        fromExample: 'örnek konum',
        change: 'Değiştir',
        assembly: 'Toplanma alanları',
        medical: 'Hastaneler',
        noAssembly: 'Bu bölge için henüz kayıtlı toplanma alanı yok.',
        noMedical: 'Bu bölge için kayıtlı hastane yok.',
        allReported: 'Bu listedeki her yer dolu veya kapalı olarak bildirildi.',
        allReportedShort: 'Hepsi dolu veya kapalı bildirildi',
        urgent: 'Acil durumda 112\'yi arayın.',
        suggested: 'Önerilen',
        walk: '~{min} yürüyüş ({m})',
        eta: 'Tahmini varış {when}',
        minutes: '{n} dk',
        noRoute: 'Bu haritada yürüme yolu bulunamadı.',
        kind: {assembly_point: 'Toplanma alanı', shelter: 'Barınma alanı', hospital: 'Hastane', clinic: 'Sağlık merkezi'},
        facility: {water: 'Su var', medical: 'İlk yardım', power: 'Elektrik / şarj', shelter: 'Çadır / barınma', accessible: 'Engelli erişimi'},
        facilitiesLabel: 'Mevcut imkanlar',
        official: 'Resmî liste',
        unofficial: 'Resmî listeden değil',
        emergencyYes: 'Acil servis var',
        emergencyNo: 'Acil servis yok',
        source: 'Kaynak: {source}. Kaynakla karşılaştırma tarihi: {date}.',
        report: {in_use: 'Kullanımda: gelenleri kabul ediyor.', full: 'Dolu: daha fazla kişi alamıyor. Başka bir yere gidin.', closed: 'Kapalı: oraya gitmeyin.',
                 none: 'Bu yerin kullanımda olup olmadığı henüz bildirilmedi.'},
        reportedAt: 'Operasyon merkezinin bildirimi: {when}.',
        reportShort: {in_use: 'Kullanımda', full: 'Dolu', closed: 'Kapalı'},
        group: {checked: 'Geçilebilir, doğrulandı', unchecked: 'Henüz doğrulanmadı', no_data: 'Bilgi yok', blocked: 'Kapalı bildirildi'},
        groupMore: {
            checked: 'bir operatör dron fotoğrafına bakıp doğruladı',
            unchecked: 'dron bir engel bulmadı, ancak henüz hiçbir operatör bakmadı',
            no_data: 'dron uçuşunun dışında ya da dron göremedi',
            blocked: '2 metreden az açıklık var. Kaçının',
        },
        verdict: {
            checked: 'Bu yoldaki her sokağın geçilebilir olduğunu bir operatör doğruladı.',
            partly: 'Bu yolun {m} kadarı doğrulanmadı. İlerlerken sokağa dikkat edin.',
            blocked: 'Bu yol, kapalı bildirilen {m} boyunca geçiyor. Yalnızca geçebileceğinizi görüyorsanız ilerleyin. Geçemiyorsanız binalardan uzak, açık bir alanda kalın ve 112\'yi arayın.',
        },
        trust: 'Harita yanlış veya eski olabilir. Gördüğünüze güvenin ve önce resmî talimatlara uyun.',
        steps: 'Adım adım',
        step: {start: 'Başlangıç: {name}', straight: 'Düz devam edin: {name}', left: 'Sola dönün: {name}', right: 'Sağa dönün: {name}',
               toStreet: 'Sokağa kadar {m} yürüyün', arrive: 'Varış: {name}', fromStreet: 'sokaktan yaklaşık {m}'},
        unnamed: {street: 'adsız sokak', footway: 'yaya yolu', steps: 'merdiven', track: 'toprak yol'},
        others: 'Diğer yerler',
        showAll: 'Tümünü göster ({n})',
        legendRoute: 'Yolunuz',
        legendDrone: 'Dronun fotoğrafladığı alan',
        legendOff: 'Dolu veya kapalı bildirilen yer',
        droneLabel: 'Dron uçuşu, {date}',
        seen: {drone: 'Dron {date} tarihinde gördü.', field_report: 'Sahadan {date} tarihinde bildirildi.'},
        confirmedOn: 'Bir operatör {date} tarihinde doğruladı.',
        notConfirmed: 'Henüz hiçbir operatör doğrulamadı.',
        width: 'Yaklaşık {m} m açıklık.',
        narrow: 'Araçlar için dar (2–3 m), yayalar için uygun.',
        simulatedEvent: 'Simülasyon olayı (gösterim).',
        received: 'Son bilginin alındığı zaman: {when}.',
        ago: {now: 'az önce', min: '{n} dk önce'},
        offline: 'Bağlantı yok. Alınan son bilgi gösteriliyor ({when}).',
        updated: 'Yeni bilgi var.',
        noticeNew: 'Sayfanın üstünde yeni bir duyuru var.',
        noticeGone: 'Duyuru geri çekildi.',
        reportGone: 'bildirim geri çekildi',
        updatedPlaces: 'Bildirimi değişen yer sayısı: {n}.',
        updatedStreets: 'Değişen sokak sayısı: {n}.',
        routeChanged: 'Yolunuz değişti.',
        routeSame: 'Yolunuz aynı kaldı.',
        mapMissing: 'Bu telefon haritayı çizemiyor. Liste ve adımlar yine de çalışır.',
        aboutWhat: 'Toplanma alanlarını ve hastaneleri, kapalı bildirilen sokaklardan kaçınan bir yürüme yoluyla birlikte gösterir. Bir sokak, ancak operasyon merkezindeki bir operatör dron fotoğrafına bakıp doğruladıktan sonra geçilebilir olarak gösterilir.',
        aboutPrivacy: 'Gizlilik: uygulama herkes için aynı dosyayı indirir ve yolu telefonunuzda bulur. Konumunuz gönderilmez ve saklanmaz. Hesap, çerez ve izleme yoktur.',
        aboutLimits: 'Sınırlar: dron uçuşunun dışındaki sokaklar hakkında bilgi yoktur. Yerler, her birinin yanında gösterilen kaynaklardan alınmıştır. Bir yerin şu anda kullanımda olup olmadığı, yalnızca operasyon merkezi bildirdiyse bilinir. Resmî talimatlar her zaman önce gelir.',
        keptLanguage: 'Bu telefon uygulamanın dilini saklar.',
        keptPack: 'Aldığı son bilgiyi saklar ve bağlantı olmadığında onu gösterir.',
        keptApp: 'Uygulamanın kendisini de saklar; böylece uygulama bağlantı olmadan da açılır.',
        aboutPrototype: 'Nature Shield ekibinin prototipidir (Yunanistan × Türkiye hackathonu). Resmî bir hizmet değildir.',
        data: 'Veri',
        legend: 'Harita neyi gösterir',
        places: 'Yerler',
        showDetails: 'Ayrıntılar',
        showMap: 'Harita',
        chooseFirst: 'Yolu görmek için nerede olduğunuzu belirtin.',
        openSource: 'Kaynağı aç',
        phone: 'Telefon',
        mobileView: 'Mobil görünüm',
        desktopView: 'Masaüstü görünümü',
        locateMe: 'Konumumu bul',
        recenterMap: 'Tüm yolu göster',
        installApp: 'Uygulamayı yükle',
        installTip: 'Telefonunuza ekleyin: Safari\'de Paylaş → Ana Ekrana Ekle; Chrome\'da Uygulamayı yükle seçeneğine dokunun.',
        navMap: 'Harita',
        navAssembly: 'Toplanma',
        navMedical: 'Hastaneler',
        voiceTitle: '112 Sesli Asistan',
        voiceConnecting: '112 asistanına bağlanılıyor…',
        voiceListening: 'Bağlandı · Dinleniyor…',
        voiceSpeaking: 'Asistan konuşuyor…',
        voiceEnded: 'Arama sonlandı',
        voiceError: 'Sesli asistana bağlanılamadı. Voice_Agents arka ucunun çalıştığından emin olun.',
        voiceMute: 'Sessize al',
        voiceUnmute: 'Sesi aç',
        voiceEnd: 'Aramayı bitir',
        voiceDial112: '112\'yi ara',
    },

    el: {
        appName: 'Ασφαλή σημεία',
        exercise: 'ΑΣΚΗΣΗ',
        exerciseShort: 'Δεν είναι πραγματική έκτακτη ανάγκη',
        exerciseTitle: 'Αυτό είναι άσκηση',
        simulated: 'Σε μερικούς δρόμους υπάρχουν προσομοιωμένα συμβάντα, φτιαγμένα για αυτή την επίδειξη.',
        call: 'Κλήση 112',
        language: 'Γλώσσα',
        about: 'Σχετικά και υπόμνημα',
        close: 'Κλείσιμο',
        loading: 'Φόρτωση της περιοχής…',
        noPack: 'Δεν υπάρχει σύνδεση και δεν έχει αποθηκευτεί ακόμη τίποτα σε αυτό το τηλέφωνο.',
        tooOld: 'Αυτή η σελίδα είναι παλιότερη από τις πληροφορίες που έλαβε. Φορτώστε την ξανά.',
        openGround: 'Πηγαίνετε σε ανοιχτό χώρο, μακριά από κτίρια, τοίχους και καλώδια ρεύματος. Σε κίνδυνο καλέστε το 112.',
        retry: 'Δοκιμή ξανά',
        notice: 'Ανακοίνωση',
        whereTitle: 'Πού βρίσκεστε;',
        whereClosest: 'Ποιο σημείο είναι πιο κοντά σας;',
        wherePrivate: 'Η θέση σας μένει σε αυτό το τηλέφωνο. Δεν στέλνεται πουθενά.',
        useGps: 'Χρήση της θέσης μου',
        chooseOnMap: 'Επιλογή στον χάρτη',
        example: 'Θέση-παράδειγμα',
        tapHint: 'Πατήστε στον χάρτη εκεί που βρίσκεστε.',
        cancel: 'Άκυρο',
        gpsWaiting: 'Αναζήτηση της θέσης σας…',
        gpsDenied: 'Το τηλέφωνο δεν έδωσε τη θέση του. Επιλέξτε τη θέση σας στον χάρτη.',
        gpsFailed: 'Η θέση σας δεν βρέθηκε. Επιλέξτε τη θέση σας στον χάρτη.',
        gpsOutside: 'Βρίσκεστε {km} από την περιοχή {area}. Το πρωτότυπο καλύπτει μόνο αυτή την περιοχή. Για να το δοκιμάσετε, επιλέξτε μια θέση στον χάρτη.',
        noStreet: 'Κανένας δρόμος του χάρτη δεν απέχει λιγότερο από {m} από αυτό το σημείο. Επιλέξτε ένα σημείο πιο κοντά σε δρόμο.',
        you: 'Βρίσκεστε εδώ. Σύρετε για μετακίνηση.',
        position: 'Η θέση σας',
        fromGps: 'από το τηλέφωνο, ± {m}',
        fromTap: 'επιλέχθηκε στον χάρτη',
        fromExample: 'θέση-παράδειγμα',
        change: 'Αλλαγή',
        assembly: 'Σημεία συγκέντρωσης',
        medical: 'Νοσοκομεία',
        noAssembly: 'Δεν υπάρχει ακόμη καταχωρισμένο σημείο συγκέντρωσης για αυτή την περιοχή.',
        noMedical: 'Δεν υπάρχει καταχωρισμένο νοσοκομείο για αυτή την περιοχή.',
        allReported: 'Κάθε σημείο αυτής της λίστας έχει αναφερθεί πλήρες ή κλειστό.',
        allReportedShort: 'Όλα αναφέρθηκαν πλήρη ή κλειστά',
        urgent: 'Σε επείγουσα ανάγκη καλέστε το 112.',
        suggested: 'Προτείνεται',
        walk: '~{min} με τα πόδια ({m})',
        eta: 'Εκτ. άφιξη {when}',
        minutes: '{n} λεπ.',
        noRoute: 'Δεν βρέθηκε διαδρομή με τα πόδια σε αυτόν τον χάρτη.',
        kind: {assembly_point: 'Σημείο συγκέντρωσης', shelter: 'Χώρος φιλοξενίας', hospital: 'Νοσοκομείο', clinic: 'Κέντρο υγείας'},
        facility: {water: 'Νερό', medical: 'Πρώτες βοήθειες', power: 'Ρεύμα / φόρτιση', shelter: 'Σκηνές / στέγη', accessible: 'Πρόσβαση ΑμεΑ'},
        facilitiesLabel: 'Διαθέσιμες παροχές',
        official: 'Επίσημη λίστα',
        unofficial: 'Όχι από επίσημη λίστα',
        emergencyYes: 'Τμήμα επειγόντων',
        emergencyNo: 'Χωρίς τμήμα επειγόντων',
        source: 'Πηγή: {source}. Συγκρίθηκε με την πηγή στις {date}.',
        report: {in_use: 'Σε λειτουργία: δέχεται κόσμο.', full: 'Πλήρες: δεν δέχεται άλλους. Πηγαίνετε σε άλλο σημείο.', closed: 'Κλειστό: μην πάτε εκεί.',
                 none: 'Δεν έχει αναφερθεί ακόμη αν αυτό το σημείο λειτουργεί.'},
        reportedAt: 'Αναφορά από το κέντρο επιχειρήσεων: {when}.',
        reportShort: {in_use: 'Σε λειτουργία', full: 'Πλήρες', closed: 'Κλειστό'},
        group: {checked: 'Επιβεβαιωμένα βατός', unchecked: 'Δεν έχει επιβεβαιωθεί ακόμη', no_data: 'Καμία πληροφορία', blocked: 'Αναφέρεται κλειστός'},
        groupMore: {
            checked: 'ένας χειριστής κοίταξε τη φωτογραφία του drone και το επιβεβαίωσε',
            unchecked: 'το drone δεν βρήκε εμπόδιο, αλλά κανένας χειριστής δεν έχει κοιτάξει ακόμη',
            no_data: 'έξω από την πτήση του drone ή το drone δεν μπόρεσε να τον δει',
            blocked: 'λιγότερο από 2 m ελεύθερα. Αποφύγετέ τον',
        },
        verdict: {
            checked: 'Κάθε δρόμος αυτής της διαδρομής επιβεβαιώθηκε βατός από χειριστή.',
            partly: '{m} αυτής της διαδρομής δεν έχουν επιβεβαιωθεί. Προσέχετε τον δρόμο καθώς προχωράτε.',
            blocked: 'Η διαδρομή περνά από {m} που αναφέρονται κλειστά. Προχωρήστε μόνο αν βλέπετε ότι μπορείτε να περάσετε. Αλλιώς μείνετε σε ανοιχτό χώρο, μακριά από κτίρια, και καλέστε το 112.',
        },
        trust: 'Ο χάρτης μπορεί να είναι λάθος ή παλιός. Εμπιστευτείτε αυτό που βλέπετε και ακολουθήστε πρώτα τις επίσημες οδηγίες.',
        steps: 'Βήμα βήμα',
        step: {start: 'Ξεκινήστε: {name}', straight: 'Συνεχίστε ευθεία: {name}', left: 'Στρίψτε αριστερά: {name}', right: 'Στρίψτε δεξιά: {name}',
               toStreet: 'Περπατήστε {m} ως τον δρόμο', arrive: 'Άφιξη: {name}', fromStreet: 'περίπου {m} από τον δρόμο'},
        unnamed: {street: 'δρόμος χωρίς όνομα', footway: 'μονοπάτι', steps: 'σκαλιά', track: 'χωματόδρομος'},
        others: 'Άλλα σημεία',
        showAll: 'Εμφάνιση όλων ({n})',
        legendRoute: 'Η διαδρομή σας',
        legendDrone: 'Περιοχή που φωτογράφισε το drone',
        legendOff: 'Σημείο που αναφέρθηκε πλήρες ή κλειστό',
        droneLabel: 'Πτήση drone, {date}',
        seen: {drone: 'Τον είδε το drone στις {date}.', field_report: 'Αναφορά από το πεδίο στις {date}.'},
        confirmedOn: 'Επιβεβαιώθηκε από χειριστή στις {date}.',
        notConfirmed: 'Κανένας χειριστής δεν τον έχει επιβεβαιώσει ακόμη.',
        width: 'Περίπου {m} m ελεύθερα.',
        narrow: 'Στενός για οχήματα (2 έως 3 m), εντάξει με τα πόδια.',
        simulatedEvent: 'Προσομοιωμένο συμβάν (επίδειξη).',
        received: 'Τελευταία λήψη πληροφοριών: {when}.',
        ago: {now: 'μόλις τώρα', min: 'πριν από {n} λεπ.'},
        offline: 'Χωρίς σύνδεση. Εμφανίζονται οι τελευταίες πληροφορίες που ελήφθησαν ({when}).',
        updated: 'Νέες πληροφορίες.',
        noticeNew: 'Νέα ανακοίνωση στο πάνω μέρος της σελίδας.',
        noticeGone: 'Η ανακοίνωση αποσύρθηκε.',
        reportGone: 'η αναφορά αποσύρθηκε',
        updatedPlaces: 'Σημεία με αλλαγή στην αναφορά: {n}.',
        updatedStreets: 'Δρόμοι που άλλαξαν: {n}.',
        routeChanged: 'Η διαδρομή σας άλλαξε.',
        routeSame: 'Η διαδρομή σας μένει η ίδια.',
        mapMissing: 'Αυτό το τηλέφωνο δεν μπορεί να σχεδιάσει τον χάρτη. Η λίστα και τα βήματα λειτουργούν.',
        aboutWhat: 'Δείχνει σημεία συγκέντρωσης και νοσοκομεία, με διαδρομή με τα πόδια που αποφεύγει τους δρόμους που αναφέρονται κλειστοί. Ένας δρόμος φαίνεται βατός μόνο αφού ένας χειριστής στο κέντρο επιχειρήσεων κοιτάξει τη φωτογραφία του drone και το επιβεβαιώσει.',
        aboutPrivacy: 'Ιδιωτικότητα: η εφαρμογή κατεβάζει το ίδιο αρχείο για όλους και βρίσκει τη διαδρομή στο τηλέφωνό σας. Η θέση σας δεν στέλνεται και δεν αποθηκεύεται. Χωρίς λογαριασμό, χωρίς cookies, χωρίς παρακολούθηση.',
        aboutLimits: 'Όρια: έξω από την πτήση του drone δεν γνωρίζουμε τίποτα για τους δρόμους. Τα σημεία προέρχονται από τις πηγές που φαίνονται δίπλα στο καθένα. Αν ένα σημείο λειτουργεί τώρα το γνωρίζουμε μόνο όπου το ανέφερε το κέντρο επιχειρήσεων. Οι επίσημες οδηγίες προηγούνται πάντα.',
        keptLanguage: 'Το τηλέφωνο κρατά τη γλώσσα της εφαρμογής.',
        keptPack: 'Κρατά τις τελευταίες πληροφορίες που έλαβε και τις δείχνει όταν δεν υπάρχει σύνδεση.',
        keptApp: 'Κρατά και την ίδια την εφαρμογή, ώστε να ανοίγει και χωρίς σύνδεση.',
        aboutPrototype: 'Πρωτότυπο της ομάδας Nature Shield (hackathon Ελλάδα × Τουρκία). Δεν είναι επίσημη υπηρεσία.',
        data: 'Δεδομένα',
        legend: 'Τι δείχνει ο χάρτης',
        places: 'Σημεία',
        showDetails: 'Λεπτομέρειες',
        showMap: 'Χάρτης',
        chooseFirst: 'Πείτε πού βρίσκεστε για να δείτε τη διαδρομή.',
        openSource: 'Άνοιγμα της πηγής',
        phone: 'Τηλέφωνο',
        mobileView: 'Προβολή κινητού',
        desktopView: 'Προβολή υπολογιστή',
        locateMe: 'Εύρεση της θέσης μου',
        recenterMap: 'Εμφάνιση όλης της διαδρομής',
        installApp: 'Εγκατάσταση εφαρμογής',
        installTip: 'Προσθήκη στο τηλέφωνο: στο Safari πατήστε Κοινοποίηση → Προσθήκη στην Οθόνη Αφετηρίας· στο Chrome πατήστε Εγκατάσταση εφαρμογής.',
        navMap: 'Χάρτης',
        navAssembly: 'Συγκέντρωση',
        navMedical: 'Νοσοκομεία',
        voiceTitle: 'Φωνητικός Βοηθός 112',
        voiceConnecting: 'Σύνδεση με τον βοηθό 112…',
        voiceListening: 'Συνδέθηκε · Ακρόαση…',
        voiceSpeaking: 'Ο βοηθός μιλάει…',
        voiceEnded: 'Η κλήση έληξε',
        voiceError: 'Αδυναμία σύνδεσης με τον φωνητικό βοηθό. Βεβαιωθείτε ότι εκτελείται το Voice_Agents backend.',
        voiceMute: 'Σίγαση',
        voiceUnmute: 'Κατάργηση σίγασης',
        voiceEnd: 'Τερματισμός',
        voiceDial112: 'Κλήση 112',
    },
};

let current = 'en';

/* The language to start in: the one chosen before on this phone, else the phone's own, else English. */
export function firstLanguage() {
    let kept = null;
    try {
        kept = localStorage.getItem('language');
    } catch {
        // a private window: nothing is kept, the phone's language decides
    }
    const wanted = [kept, ...(navigator.languages || [navigator.language || ''])].map(code => (code || '').slice(0, 2).toLowerCase());
    return wanted.find(code => code in TEXT) || 'en';
}

export function setLanguage(code) {
    current = code in TEXT ? code : 'en';
    try {
        localStorage.setItem('language', current);
    } catch {
        // not kept: fine
    }
    return current;
}

export const language = () => current;

const find = (texts, key) => key.split('.').reduce((part, word) => (part == null ? part : part[word]), texts);

/* The text of `key` in the current language, with {words} filled in from `values`. */
export function t(key, values = {}) {
    const text = find(TEXT[current], key) ?? find(TEXT.en, key) ?? key;
    return text.replace(/\{(\w+)\}/g, (whole, word) => (word in values ? values[word] : whole));
}

/* What the pack says in several languages ({en: ..., tr: ...}): ours, else English, else whatever there is. */
export const said = texts => (texts ? texts[current] ?? texts.en ?? Object.values(texts)[0] ?? '' : '');

/* What to call a street: its name, or what kind of way it is when it has none. */
export function streetName(name, kind) {
    if (name) return name;
    const paths = ['footway', 'path', 'pedestrian', 'cycleway'];
    return t(`unnamed.${kind === 'steps' || kind === 'track' ? kind : paths.includes(kind) ? 'footway' : 'street'}`);
}

/* A distance, rounded the way people say it: 35 m, 640 m, 1.2 km, 1,116 km. */
export function metres(m) {
    if (m < 100) return `${Math.max(5, Math.round(m / 5) * 5)} m`;
    if (m < 995) return `${Math.round(m / 10) * 10} m`;
    return `${new Intl.NumberFormat(current, {maximumFractionDigits: m < 20000 ? 1 : 0}).format(m / 1000)} km`;
}

export const minutes = seconds => t('minutes', {n: Math.max(1, Math.round(seconds / 60))});

export const number = (value, digits = 1) => new Intl.NumberFormat(current, {maximumFractionDigits: digits}).format(value);

/* "9 Feb 2023" from a time, or from a day written as 2026-11-12. */
export function day(value) {
    const plainDay = typeof value === 'string' && value.length === 10;
    return new Intl.DateTimeFormat(current, {day: 'numeric', month: 'short', year: 'numeric', ...(plainDay ? {timeZone: 'UTC'} : {})})
        .format(new Date(value));
}

/* "14:05", or "12 Nov, 14:05" when it was not today. The 24-hour clock in every language: "12:58 AM" is read as noon
   by many, and it is the clock Türkiye and Greece write. */
export function clock(value) {
    const time = new Date(value), today = new Date().toDateString() === time.toDateString();
    return new Intl.DateTimeFormat(current, {hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
                                             ...(today ? {} : {day: 'numeric', month: 'short'})}).format(time);
}

/* "3 min ago"; after an hour the time itself ("14:05"), which says more than "2 h ago". */
export function ago(value, now = Date.now()) {
    const min = Math.floor((now - new Date(value).getTime()) / 60000);
    if (min < 1) return t('ago.now');
    return min < 60 ? t('ago.min', {n: min}) : clock(value);
}

/* Every key of every language, for the tests: each language must say everything English says. */
export function keys(code) {
    const list = [];
    const walk = (part, path) => {
        for (const [word, value] of Object.entries(part)) {
            if (typeof value === 'string') list.push(path + word);
            else walk(value, `${path}${word}.`);
        }
    };
    walk(TEXT[code], '');
    return list.sort();
}
