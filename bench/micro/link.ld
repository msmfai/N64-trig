OUTPUT_ARCH(mips)
ENTRY(_start)
SECTIONS
{
    . = 0x80000400;
    .text : { *(.text.start) *(.text*) }
    .rodata : { *(.rodata*) *(.rdata*) }
    .data : { *(.data*) *(.sdata*) *(.lit4) *(.lit8) }
    . = ALIGN(16);
    __bss_start = .;
    .bss (NOLOAD) : { *(.sbss*) *(.scommon) *(.bss*) *(COMMON) }
    . = ALIGN(16);
    __bss_end = .;
    /DISCARD/ : { *(.mdebug*) *(.comment) *(.reginfo) *(.MIPS.*) *(.gptab*) *(.pdr) *(.options) *(.note*) }
}
