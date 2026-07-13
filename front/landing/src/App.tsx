import { Button } from '@/components/ui/button'
import heroBg from '@/assets/hero-bg.jpg'

const APP_URL = '/app'

const displayFont = { fontFamily: "'Instrument Serif', serif" }

function App() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-background text-foreground">
      <img
        src={heroBg}
        alt=""
        className="absolute inset-0 z-0 h-full w-full object-cover"
      />
      <div className="absolute inset-0 z-0 bg-background/40" />

      <nav className="relative z-10 mx-auto flex max-w-7xl flex-row items-center justify-between px-8 py-6">
        <span className="text-3xl tracking-tight text-foreground" style={displayFont}>
          Anki Lite
        </span>
        <div className="hidden items-center gap-8 md:flex">
          <a href="/" className="text-sm text-foreground transition-colors hover:text-foreground">
            Главная
          </a>
          <a href={APP_URL} className="text-sm text-muted-foreground transition-colors hover:text-foreground">
            Тренировка
          </a>
          <a href="#about" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
            О сервисе
          </a>
        </div>
        <a href={APP_URL}>
          <Button variant="glass" className="rounded-full px-6 py-2.5 text-sm">
            Начать
          </Button>
        </a>
      </nav>

      <section className="relative z-10 flex flex-col items-center px-6 py-[90px] pt-32 pb-40 text-center">
        <h1
          className="animate-fade-rise max-w-7xl text-5xl leading-[0.95] font-normal tracking-[-2.46px] sm:text-7xl md:text-8xl"
          style={displayFont}
        >
          Английский, <em className="text-muted-foreground not-italic">который остаётся с тобой</em>.
        </h1>
        <p className="animate-fade-rise-delay mt-8 max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-lg">
          Персональный тренажёр на интервальном повторении: система сама находит слова, которые вы
          забываете, объясняет ошибки на живых примерах и подстраивается под ваш уровень — с
          помощью AI.
        </p>
        <a href={APP_URL} className="animate-fade-rise-delay-2 mt-12">
          <Button variant="glass" size="lg" className="cursor-pointer rounded-full px-14 py-5 text-base">
            Начать
          </Button>
        </a>
      </section>
    </div>
  )
}

export default App
