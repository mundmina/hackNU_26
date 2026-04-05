import { useState } from "react";

import type { AlertItem } from "../types";

interface AlertFeedProps {
  alerts: AlertItem[];
}

const ALERT_MESSAGES: Record<string, string> = {
  WHEEL_SLIP: "Проскальзывание колёс выше 3%",
  OIL_TEMP_HIGH: "Температура моторного масла выше безопасного порога",
  COOLANT_HIGH: "Температура охлаждающей жидкости повышается",
  BRAKE_PRESSURE_LOW: "Давление в главном резервуаре ниже безопасного диапазона",
  BRAKE_PAD_LOW: "Ресурс тормозных колодок ниже порога обслуживания",
  ERROR_CODES_ACTIVE: "Бортовой контроллер сообщает об активных кодах ошибок",
  CATENARY_VOLTAGE_ABNORMAL: "Напряжение контактной сети вне рабочего диапазона (19–29 кВ)",
  BATTERY_VOLTAGE_LOW: "Напряжение вспомогательной батареи ниже безопасного порога",
  HEALTH_INDEX_LOW: "Индекс технического состояния снижен",
};

const ALERT_RECOMMENDATIONS: Record<string, string> = {
  WHEEL_SLIP:
    "Плавно снизьте тяговое усилие. При наличии подайте песок. Уменьшите тягу и дайте скорости колёс стабилизироваться перед повторным набором мощности. Если проскальзывание держится выше 6%, включите аварийный противобуксовочный режим и сообщите диспетчеру.",
  OIL_TEMP_HIGH:
    "Снизьте тяговое усилие и скорость, чтобы уменьшить нагрузку на двигатель. Проверьте работу вентиляторов масляного охлаждения. Если температура превысила 120 °C, выполните плановую остановку и сообщите в обслуживание. Не глушите двигатель резко: дайте ему поработать на холостом ходу 5 минут для охлаждения.",
  COOLANT_HIGH:
    "Немедленно уменьшите нагрузку на двигатель. Проверьте уровень охлаждающей жидкости и работу вентиляторов. Если температура не снижается в течение 5 минут, остановитесь в ближайшем безопасном месте. Не открывайте крышку радиатора на горячей системе.",
  BRAKE_PRESSURE_LOW:
    "Снизьте скорость и увеличьте тормозной путь. Дайте компрессору восстановить давление в резервуаре и избегайте повторных полных торможений. Если давление опустится ниже 0,62 МПа, затяните стояночный тормоз и остановитесь. Сообщите диспетчеру и не продолжайте движение до восстановления давления.",
  BRAKE_PAD_LOW:
    "Сообщите о степени износа в обслуживание на следующей остановке. В качестве меры предосторожности увеличьте тормозной путь на 20%. Избегайте экстренного торможения. Запланируйте замену колодок до следующего рейса.",
  ERROR_CODES_ACTIVE:
    "Зафиксируйте коды ошибок, отображаемые на пульте. Сверьтесь с карточкой неисправностей для конкретного кода. Если неисправность относится к критическим по безопасности, сообщите диспетчеру и снизьте скорость. Запишите все активные коды в журнал поездки.",
  CATENARY_VOLTAGE_ABNORMAL:
    "При наличии переключитесь на вспомогательный режим питания. Уменьшите токопотребление токоприёмника, снизив тяговое усилие. Если напряжение упало ниже 19 кВ или поднялось выше 29 кВ, опустите токоприёмник и остановитесь накатом. Сообщите диспетчеру и дождитесь решения инфраструктурной службы.",
  BATTERY_VOLTAGE_LOW:
    "Отключите второстепенные вспомогательные системы, например отопление кабины и лишнее освещение. Проверьте состояние зарядки батареи на пульте. Если напряжение упадёт ниже 94 В, возможен отказ вспомогательных цепей управления: остановитесь на ближайшей станции и вызовите обслуживание.",
  HEALTH_INDEX_LOW:
    "При оценке D снизьте скорость на 20% и избегайте резких разгонов и торможений. Сообщите диспетчеру об ухудшении технического состояния. При оценке E необходимо выполнить контролируемую остановку в ближайшем безопасном месте и не продолжать рейс до осмотра локомотива.",
};

const ALERT_SOURCES: Record<string, string> = {
  traction: "тяга",
  engine: "двигатель",
  cooling: "охлаждение",
  brakes: "тормоза",
  control: "управление",
  power: "питание",
  "health-index": "индекс состояния",
};

export function AlertFeed({ alerts }: AlertFeedProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  function toggle(id: string) {
    setExpandedId((current) => (current === id ? null : id));
  }

  return (
    <section className="panel alert-panel">
      <div className="panel-header">
        <p>Лента предупреждений</p>
        <span className="muted">{alerts.length} активных</span>
      </div>
      <div className="alert-list">
        {alerts.length === 0 ? (
          <div className="empty-state">Активных предупреждений нет. Система фиксирует штатную работу.</div>
        ) : (
          alerts.map((alert) => {
            const isExpanded = expandedId === alert.alert_id;
            return (
              <article key={alert.alert_id} className={`alert-card severity-${alert.severity}`}>
                <button
                  className="alert-topline alert-toggle"
                  onClick={() => toggle(alert.alert_id)}
                  aria-expanded={isExpanded}
                >
                  <strong>{ALERT_MESSAGES[alert.code] ?? alert.message}</strong>
                  <span className="alert-right">
                    <span className="alert-time">{new Date(alert.timestamp).toLocaleTimeString("ru-RU")}</span>
                    <span className="alert-chevron">{isExpanded ? "▲" : "▼"}</span>
                  </span>
                </button>
                <div className="alert-meta">
                  <span>{alert.code}</span>
                  <span>{ALERT_SOURCES[alert.source] ?? alert.source}</span>
                </div>
                {isExpanded && (ALERT_RECOMMENDATIONS[alert.code] ?? alert.recommendation) ? (
                  <div className="alert-recommendation">
                    <p className="recommendation-label">Действия машиниста</p>
                    <p className="recommendation-text">{ALERT_RECOMMENDATIONS[alert.code] ?? alert.recommendation}</p>
                  </div>
                ) : null}
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}
