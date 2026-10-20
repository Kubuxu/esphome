"""LEDC PWM outputs.

On ESP32-C3, ``dithering: true`` enables four fractional duty bits averaged over
16 PWM periods without changing the carrier frequency. It is disabled by default
and remains active at steady brightness, not just during light transitions.
At low PWM frequencies the 16-period pattern can introduce visible flicker.
"""

from typing import Any

from esphome import automation, pins
import esphome.codegen as cg
from esphome.components import esp32, output
from esphome.components.esp32 import include_builtin_idf_component
import esphome.config_validation as cv
from esphome.const import (
    CONF_CHANNEL,
    CONF_FREQUENCY,
    CONF_ID,
    CONF_PHASE_ANGLE,
    CONF_PIN,
)
from esphome.core import ID
from esphome.cpp_generator import MockObj, TemplateArgsType
from esphome.types import ConfigType

DEPENDENCIES = ["esp32"]

CONF_DITHERING = "dithering"


def calc_max_frequency(bit_depth: int) -> float:
    return 80e6 / (2**bit_depth)


def calc_min_frequency(bit_depth: int) -> float:
    max_div_num = ((2**20) - 1) / 256.0
    return 80e6 / (max_div_num * (2**bit_depth))


def validate_frequency(value: Any) -> float:
    value = cv.frequency(value)
    min_freq = calc_min_frequency(20)
    max_freq = calc_max_frequency(1)
    if value < min_freq:
        raise cv.Invalid(
            f"This frequency setting is not possible, please choose a higher frequency (at least {int(min_freq)}Hz)"
        )
    if value > max_freq:
        raise cv.Invalid(
            f"This frequency setting is not possible, please choose a lower frequency (at most {int(max_freq)}Hz)"
        )
    return value


ledc_ns = cg.esphome_ns.namespace("ledc")
LEDCOutput = ledc_ns.class_("LEDCOutput", output.FloatOutput, cg.Component)
SetFrequencyAction = ledc_ns.class_("SetFrequencyAction", automation.Action)

CONFIG_SCHEMA = output.FLOAT_OUTPUT_SCHEMA.extend(
    {
        cv.Required(CONF_ID): cv.declare_id(LEDCOutput),
        cv.Required(CONF_PIN): pins.internal_gpio_output_pin_schema,
        cv.Optional(CONF_FREQUENCY, default="1kHz"): cv.All(
            cv.frequency, cv.float_range(min=0, min_included=False)
        ),
        cv.Optional(CONF_CHANNEL): cv.int_range(min=0, max=15),
        cv.Optional(CONF_DITHERING): cv.All(
            cv.boolean,
            esp32.only_on_variant(
                supported=[esp32.VARIANT_ESP32C3],
                msg_prefix="LEDC hardware dithering",
            ),
        ),
        cv.Optional(CONF_PHASE_ANGLE): cv.All(
            cv.angle, cv.float_range(min=0.0, max=360.0)
        ),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config: ConfigType) -> None:
    # Re-enable the LEDC driver (excluded by default to save compile time)
    include_builtin_idf_component("esp_driver_ledc")

    gpio = await cg.gpio_pin_expression(config[CONF_PIN])
    var = cg.new_Pvariable(config[CONF_ID], gpio)
    await cg.register_component(var, config)
    await output.register_output(var, config)
    if CONF_CHANNEL in config:
        cg.add(var.set_channel(config[CONF_CHANNEL]))
    cg.add(var.set_frequency(config[CONF_FREQUENCY]))
    if CONF_PHASE_ANGLE in config:
        cg.add(var.set_phase_angle(config[CONF_PHASE_ANGLE]))
    if (dithering := config.get(CONF_DITHERING)) is not None:
        cg.add(var.set_dithering(dithering))


@automation.register_action(
    "output.ledc.set_frequency",
    SetFrequencyAction,
    cv.Schema(
        {
            cv.Required(CONF_ID): cv.use_id(LEDCOutput),
            cv.Required(CONF_FREQUENCY): cv.templatable(validate_frequency),
        }
    ),
    synchronous=True,
)
async def ledc_set_frequency_to_code(
    config: ConfigType,
    action_id: ID,
    template_arg: cg.TemplateArguments,
    args: TemplateArgsType,
) -> MockObj:
    paren = await cg.get_variable(config[CONF_ID])
    var = cg.new_Pvariable(action_id, template_arg, paren)
    template_ = await cg.templatable(config[CONF_FREQUENCY], args, cg.float_)
    cg.add(var.set_frequency(template_))
    return var
