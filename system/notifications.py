"""Optional Windows notification. Notification failures never affect collection."""
import logging
import sys
import threading


def notify_verification():
    def send():
        try:
            if sys.platform != 'win32':
                logging.getLogger(__name__).debug('Windows upozornění není na této platformě dostupné.')
                return
            from windows_toasts import WindowsToaster, Toast
            toast = Toast()
            toast.text_fields = ['WebScraper', 'Vyžaduje ověření. Otevřete Prohlížeč v levé liště a dokončete CAPTCHA.']
            WindowsToaster('WebScraper').show_toast(toast)
        except Exception:
            logging.getLogger(__name__).warning('Windows upozornění se nepodařilo zobrazit.', exc_info=True)
    try:
        threading.Thread(target=send, name='verification-notification', daemon=True).start()
    except Exception:
        logging.getLogger(__name__).warning('Vlákno Windows upozornění se nepodařilo spustit.', exc_info=True)
