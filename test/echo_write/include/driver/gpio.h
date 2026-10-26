#pragma once
using gpio_num_t=int;
constexpr int GPIO_MODE_INPUT=1,GPIO_FLOATING=0;
int gpio_reset_pin(gpio_num_t);
int gpio_set_direction(gpio_num_t,int);
int gpio_set_pull_mode(gpio_num_t,int);
